#!/bin/sh

if [ "$(id -u)" != "0" ]; then
   echo "Installer must be run as root" 1>&2
   exit 1
fi

SOURCE="$0"
while [ -h "$SOURCE" ]; do
  DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"

pip install -r $DIR/requirements.txt > /tmp/pi-monitor-adsb-pip.log 2>&1

if [ $? != 0 ]; then
    echo "Failed to install python dependencies" 1>&2
    exit 1
fi

MONITOR_ROOT=/usr/local/pi-monitor-adsb

if [ -d "$MONITOR_ROOT" ]; then
    echo "Cleaning up previous install..."

    rm -rf $MONITOR_ROOT/bin > /dev/null 2>&1
    rm -rf $MONITOR_ROOT/lib > /dev/null 2>&1
    rm /lib/systemd/system/pi-monitor-adsb.service > /dev/null 2>&1
    rm /usr/local/bin/pi-monitor-adsb > /dev/null 2>&1
fi

mkdir -p $MONITOR_ROOT > /dev/null 2>&1
mkdir -p $MONITOR_ROOT/bin > /dev/null 2>&1
mkdir -p $MONITOR_ROOT/lib > /dev/null 2>&1
mkdir -p $MONITOR_ROOT/etc > /dev/null 2>&1

cp $DIR/bin/* $MONITOR_ROOT/bin
cp $DIR/lib/* $MONITOR_ROOT/lib
cp $DIR/etc/* $MONITOR_ROOT/etc
cp $DIR/pi-monitor-adsb.service /lib/systemd/system/pi-monitor-adsb.service

ln -s $MONITOR_ROOT/bin/pi-monitor-adsb /usr/local/bin/pi-monitor-adsb > /dev/null 2>&1