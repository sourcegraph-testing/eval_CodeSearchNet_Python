__author__ = 'Milinda Pathirage'

import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
import json
import zipfile
import os


def get_oauth2_token(token_endpoint, client_id, client_secret):
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    # request body
    values = {'grant_type': 'client_credentials',
              'client_id': client_id,
              'client_secret': client_secret}

    body = urllib.parse.urlencode(values)

    # request method must be POST
    req = urllib.request.Request(token_endpoint, body, headers)
    try:
        # urllib2 module sends HTTP/1.1 requests with Connection:close header included
        response = urllib.request.urlopen(req)

        # any other response code means the OAuth2 authentication failed. raise exception
        if response.code != 200:
            raise urllib.error.HTTPError(response.url, response.code, response.read(), response.info(), response.fp)

        # response body is a JSON string
        oauth2_token_response_string = response.read()

        # parse JSON string using python built-in json lib
        oauth2_token_response_json = json.loads(oauth2_token_response_string)

        # return the access token
        return oauth2_token_response_json["access_token"]

    # response code in the 400-599 range will raise HTTPError
    except urllib.error.HTTPError as e:
        # just re-raise the exception
        raise Exception(str(e.code) + " " + str(e.reason) + " " + str(e.info) + " " + str(e.read()))


def unzip(zip_content, dest_dir):
    # From http://stackoverflow.com/a/12886818
    with zipfile.ZipFile(zip_content, "r") as zf:
        for member in zf.infolist():
            # Path traversal defense copied from
            # http://hg.python.org/cpython/file/tip/Lib/http/server.py#l789
            words = member.filename.split('/')
            path = dest_dir
            for word in words[:-1]:
                drive, word = os.path.splitdrive(word)
                head, word = os.path.split(word)

                if word in (os.curdir, os.pardir, ''):
                    continue

                path = os.path.join(path, word)

            zf.extract(member, path)