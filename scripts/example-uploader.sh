#!/bin/sh
# Copy this example to my-uploader.sh, and edit user@host:/path
# Remember to create the folder first on your web server
cd $(dirname $0)
rsync -vacz -e ssh ../static/nest/* me@example.com:/home/me/public_html/mynest/
