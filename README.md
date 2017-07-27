# Google Drive Merge Tool

This tool lets you upload a local file/directory to a Google Drive folder, handling file name merge conflicts. 

I had my reasons for doing this.

## Requirements

- [Google Python API Client](https://developers.google.com/api-client-library/python/start/get_started)
- Download your [Google API Credentials](https://console.developers.google.com/apis/credentials) as `client_secrets.json` in the current directory

## Usage

```
usage: merge.py [-h] [-o OBJECTID] [-s SOURCE] [-r] [-m] [-d] action

positional arguments:
  action                list, upload

optional arguments:
  -h, --help            show this help message and exit
  -o OBJECTID, --objectId OBJECTID
                        Google Drive object ID to operate on
  -s SOURCE, --source SOURCE
  -r, --recursive       Recursive upload
  -m, --merge           Merge on upload
  -d, --dryRun          Perform dry run. Don't upload anything
```

## Examples

Recursively list files in a directory:

`./merge.py list -r -o 0B018HJxRh79Mam4y12345678`

Upload a single file to a directory:

`./merge.py upload -s file.txt -o 0B018HJxRh79Mam4y12345678A`

Recursively merge a directory into a Google Drive folder:

`./merge.py upload -rm -s myDirectory -o 0B018HJxRh79Mam4y12345678A`

Dry-run a recursive merge on a directory:

`./merge.py upload -drm -s myDirectory -o 0B018HJxRh79Mam4y12345678A`

