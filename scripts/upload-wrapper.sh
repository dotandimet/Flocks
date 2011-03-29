#!/bin/sh
cd $(dirname $0)
if [ -x my-uploader.sh ]; then
    echo uploading your nest...
    ./my-uploader.sh
else
    echo You now need to manually upload your nest folder \(by default: static/nest/\)
    echo to the web server, so that it's available at the nest's url.
    echo You can automate this by creating a script called '"'scripts/my-uploader.sh'"'
    echo that does this. See example at scripts/example-uploader.sh
fi
echo -n Hit Enter...
head -1 > /dev/null
