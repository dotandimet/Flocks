#!/bin/sh
cd $(dirname $0)
if [ -x upload-wrapper.sh ]; then
    xterm -title "Flocks: upload to nest" -e ./upload-wrapper.sh
else
    xterm -title "Flocks: can't find script" -hold -e echo 'Error! Missing script: scripts/upload-wrapper.sh'
fi
