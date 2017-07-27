#!/usr/bin/env python

import argparse
import httplib2
import json
import mimetypes
import os
import random
import time

from apiclient import discovery, errors
from apiclient.http import BatchHttpRequest, MediaFileUpload
from oauth2client import client
from oauth2client.file import Storage

drive_service = None

def main():
  global drive_service

  parser=argparse.ArgumentParser()
  parser.add_argument('action', type=str, help="list, upload")
  parser.add_argument('-o', '--objectId', type=str, default=None, help='Google Drive object ID to operate on')
  parser.add_argument('-s', '--source', type=str, required=False)
  parser.add_argument('-r', '--recursive', action='store_true', default=False, help='Recursive upload')
  parser.add_argument('-m', '--merge', action='store_true', default=False, help='Merge on upload')
  parser.add_argument('-d', '--dryRun', action='store_true', default=False, help='Perform dry run. Don\'t upload anything')
  args = parser.parse_args()

  drive_service = auth()

  doAction(args)

# Upload from source (local) to dest (Google) with flags
def doAction(args,):
  global drive_service

  if not drive_service:
    print "Drive Service not available"
    return

  if args.dryRun:
    print ">> THIS IS A DRY RUN. NOTHING WILL BE CREATED OR UPLOADED << "

  # Default to 'root' if no folder provided
  parent = args.objectId if args.objectId else 'root'

  # List all objects in a folder
  if args.action.lower() == "list":
    listChildren(parent, args.recursive)

  # Upload from local directory
  elif args.action.lower() == "upload":
    if args.recursive:
      uploadRecursive(args.source, parent, args.merge, args.dryRun)
    else:
      uploadSingle(args.source, parent, args.merge, args.dryRun)

  # Unknown command
  else:
    print "Unknown action '%s'" % action

# List children in Folder
def listChildren(folderId, recursive=False, prefix=''):
  pageToken = None
  while True:
    try:
      param = {}
      if pageToken:
        param['pageToken'] = pageToken

      query = "'%s' in parents" % folderId
      children = apiTryBackoff(drive_service.files().list(q=query, **param))

      for child in children.get('items', []):
        print prefix + child['id'] + " " + child['title']

        # Explore child if it is a folder
        if recursive and child['mimeType'] == 'application/vnd.google-apps.folder':
          listChildren(child['id'], recursive=True, prefix=prefix+'--')

      pageToken = children.get('nextPageToken')
      if not pageToken:
        break
    except errors.HttpError, error:
      print "Error listing children: %s" % error
      raise

# Upload
def uploadSingle(source, folderId, merge, dryRun):

  # First, get remote contents and determine if the file name exists
  baseName = os.path.basename(source)

  childId = None
  # Only check if we're merging or dryrun (for purposes of recursively searching)
  if merge or dryRun:
    children = findChildrenInFolder(baseName, folderId)
    if len(children) > 0:
      childId = children[0][1]

  # Upload the file if it doesn't exist or merge is false
  if not childId or not merge:
    fileMetadata = {
      'title': baseName,
      'parents': [ { 'id': folderId } ]
    }
    # Make folder if the uploading file is a directory
    if os.path.isdir(source):

      if not dryRun:
        print "Creating folder %s in %s" % (baseName, folderId)
        fileMetadata['mimeType'] = 'application/vnd.google-apps.folder'
        childId = apiTryBackoff(drive_service.files().insert(
          body=fileMetadata,
          fields='id')).get('id')

        print "Created file ID: ", childId
      else:
        print "[DRY] Creating folder '%s' in %s" % (baseName, folderId)

    else:
      # Guess MIME type
      (mimetype, encoding) = mimetypes.guess_type(source)

      if not dryRun:
        print "Uploading %s (%s) to %s" % (baseName, mimetype, folderId)
        media = MediaFileUpload(source, mimetype=mimetype)
        childId = apiTryBackoff(drive_service.files().insert(
          body=fileMetadata,
          media_body=media, fields='id')).get('id')

        print "Created file ID: ", childId
      else:
        print "[DRY] Uploading '%s' (%s) to %s" % (baseName, mimetype, folderId)

  else:
    print "Skipping upload:", baseName

  return childId

# Recursively upload
def uploadRecursive(source, folderId, merge, dryRun, fileId=None):

  # Use existing fileId if provided for us
  newFileId = fileId if fileId else uploadSingle(source, folderId, merge, dryRun)

  # Only if this is a dry run should this ever happen
  if newFileId is None:
    if dryRun:
      return
    else:
      raise Exception("newFileId is None and not a dry run!")

  # Recursively upload contents
  if os.path.isdir(source):

    print "Entering %s" % source

    localFiles = os.listdir(source)

    # Optimization to check all files at once
    if merge:
      # Find children with fileIds
      children = findChildrenInFolder(localFiles, newFileId)
      
      # We pass in the file ID so that we don't check again if we need to upload
      for file, fid in children:
        if fid:
          print "Skipping upload:", os.path.join(source, file)
        uploadRecursive(os.path.join(source, file), newFileId, merge, dryRun, fid)

    else:
      for file in localFiles:
        uploadRecursive(os.path.join(source, file), newFileId, merge, dryRun)      


# Returns a list of tuples with format (filename, fileId) that exist in remote
# folder. An None fileId indicates that the remote file doesn't exist.
def findChildrenInFolder(baseNames, folderId):
  pageToken = None

  # Keep track of all children
  remoteChildren = []

  # Convert single member to list
  if type(baseNames) is str:
    baseNames = [baseNames]

  namesCopy = baseNames[:]

  while True:
    try:
      param = {}
      if pageToken:
        param['pageToken'] = pageToken

      query = "'%s' in parents" % folderId
      children = apiTryBackoff(drive_service.files().list(q=query, **param))

      # For every remote file that matches a local file, add it to the list
      for child in children.get('items', []):
        if child['title'] in namesCopy:
          remoteChildren.append((child['title'], child['id']))
          namesCopy.remove(child['title'])

      pageToken = children.get('nextPageToken')
      if not pageToken:
        break
    except errors.HttpError, error:
      print "Error listing children: %s" % error
      raise

  # Add basenames that didn't appear
  for name in namesCopy:
    remoteChildren.append((name, None))

  return remoteChildren



# Try API function with backoff
def apiTryBackoff(apiCall):
  waitTime = 1
  maxBackoff = 32
  
  while True:
    try:
      return apiCall.execute()
    except errors.HttpError, error:
      if error.resp.status == 403:
        sleepytime = waitTime + random.random()
        print "403 rate limit error. Waiting for %fs" % sleepytime
        time.sleep(sleepytime)
        waitTime = min(waitTime * 2, maxBackoff)
      else:
        raise

def auth():
  credentials = None

  # Load cached credentials
  storage = Storage('credentials')
  credentials = storage.get()

  # Get credentials if not available
  if not credentials:

    flow = client.flow_from_clientsecrets(
      'client_secrets.json',
      scope='https://www.googleapis.com/auth/drive',
      redirect_uri='urn:ietf:wg:oauth:2.0:oob')

    auth_uri = flow.step1_get_authorize_url()
    print "GO to URL:\n", auth_uri

    auth_code = raw_input('Enter the auth code: ')

    # Get credentials and save to storage
    credentials = flow.step2_exchange(auth_code)
    storage.put(credentials)

  # Build service and return
  http_auth = credentials.authorize(httplib2.Http())
  drive_service = discovery.build('drive', 'v2', http_auth)

  return drive_service


if __name__ == '__main__':
  main()
  