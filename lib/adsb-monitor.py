import os
import sys

from adsb import AdsbScreen
from monitor import RpiMonitor


class AdsbMonitor(RpiMonitor):
    def __init__(self):
        RpiMonitor.__init__(self)

    def run(self):
        # Look for dump1090 specific config in these locations
        config_locations = [
            '/usr/local/pi-monitor-adsb/etc/config.cfg',
            os.path.expanduser('~/.pi-monitor/adsb.cfg')
        ]

        # Load this config
        for config_location in config_locations:
            self.load_config(config_location)

        # Create the screen and register it
        adsb = AdsbScreen(self.config.get('dump1090', 'host'),
                          self.config.getint('dump1090', 'port'),
                          self.config.getint('dump1090', 'socket_timeout'))
        self.register(adsb, index=0)

        # Call the parent run() method to get things going
        RpiMonitor.run(self)

if __name__ == '__main__':
    try:
        monitor = AdsbMonitor()
        monitor.run()
    except KeyboardInterrupt:
        print 'Shutting down monitor'
        sys.exit(0)
