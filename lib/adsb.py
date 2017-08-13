import errno
import socket
import threading
import time
from collections import deque

import dateutil.parser

from luma.core.render import canvas

from renderers import BarRenderer
from renderers import LabeledBarRenderer
from renderers import RendererConfig
from screens import Screen

lock = threading.Lock()
timer = None

class SBS1Message(object):
    def __init__(self, data):
        parts = data.split(',')

        self.is_valid = True
        self.message_type = self.parse_string(parts, 0)

        if self.message_type != "MSG":
            self.message_type = None
            self.is_valid = False

        self.tx_type = self.parse_int(parts, 1)
        self.session_id = self.parse_string(parts, 2)
        self.aircraft_id = self.parse_string(parts, 3)
        self.icao24 = self.parse_string(parts, 4)
        self.flight_id = self.parse_string(parts, 5)
        self.generated_date = self.parse_datetime(parts, 6, 7)
        self.logged_date = self.parse_datetime(parts, 8, 9)
        self.callsign = self.parse_string(parts, 10)

        if self.callsign:
            self.callsign = self.callsign.strip()

        self.altitude = self.parse_int(parts, 11)
        self.ground_speed = self.parse_int(parts, 12)
        self.track = self.parse_int(parts, 13)
        self.lat = self.parse_float(parts, 14)
        self.lon = self.parse_float(parts, 15)
        self.vertical_rate = self.parse_int(parts, 16)
        self.squawk = self.parse_int(parts, 17)
        self.alert = self.parse_bool(parts, 18)
        self.emergency = self.parse_bool(parts, 19)
        self.spi = self.parse_bool(parts, 20)
        self.on_ground = self.parse_bool(parts, 21)

    def parse_string(self, array, index):
        try:
            return None if len(array[index]) == 0 else array[index]
        except (ValueError, TypeError, IndexError):
            return None

    def parse_bool(self, array, index):
        try:
            return bool(int(array[index]))
        except (ValueError, TypeError, IndexError):
            return None

    def parse_int(self, array, index):
        try:
            return int(array[index])
        except (ValueError, TypeError, IndexError):
            return None

    def parse_float(self, array, index):
        try:
            return float(array[index])
        except (ValueError, TypeError, IndexError):
            return None

    def parse_datetime(self, array, date_index, time_index):
        d = self.parse_string(array, date_index)
        t = self.parse_string(array, time_index)

        if d is not None and t is not None:
            try:
                return dateutil.parser.parse("%s %s" % (d, t))
            except ValueError:
                return None


class AdsbScreen(Screen):

    def __init__(self, host, port, socket_timeout=2):
        Screen.__init__(self)

        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout

        self.measures = {
            'messages': deque(maxlen=31),
            'planes': deque(maxlen=31),
            'message_types': {
                'SEL': deque(maxlen=31),
                'ID':  deque(maxlen=31),
                'AIR': deque(maxlen=31),
                'STA': deque(maxlen=31),
                'CLK': deque(maxlen=31),
                'MSG': deque(maxlen=31)
            },
            'transmission_types': {
                '1': deque(maxlen=31),
                '2': deque(maxlen=31),
                '3': deque(maxlen=31),
                '4': deque(maxlen=31),
                '5': deque(maxlen=31),
                '6': deque(maxlen=31),
                '7': deque(maxlen=31),
                '8': deque(maxlen=31)
            },
            'errors': {
                'no_data': deque(maxlen=31),
                'unknown': deque(maxlen=31)
            }
        }
        self.screen_config = [
            RendererConfig(BarRenderer(), 'messages', 'Messages', x_start=126, x_step=-4),
            RendererConfig(BarRenderer(), 'planes', 'Planes', x_start=126, x_step=-4),
            RendererConfig(LabeledBarRenderer(), 'message_types', 'Message Types', x_start=2, x_step=22),
            RendererConfig(LabeledBarRenderer(), 'transmission_types', 'Transmission Types', x_start=8, x_step=15),
            RendererConfig(LabeledBarRenderer(), 'errors', 'Errors', x_start=10, x_step=66)
        ]
        self.screen_index = 0

        # Initialize some sane defaults for measures
        self.measures['messages'].append(0)
        self.measures['planes'].append(0)

    def next_screen(self):
        self.screen_index = self.screen_index + 1 if self.screen_index + 1 < len(self.screen_config) else 0

    def previous_screen(self):
        self.screen_index = self.screen_index - 1 if self.screen_index - 1 >= 0 else len(self.screen_config) - 1

    def reset_screen(self):
        self.screen_index = 0

    def sleep_interval(self):
        return 5

    def get_default_header(self, config, data):
        return '%s:%s' % (config.name, data[config.measure][-1])

    def count_max(self, config, data):
        return float(max(max([sum(q) for q in data[config.measure].values()]), 100))

    def get_trx_keys(self, config, data):
        return [str(k) for k in sorted(data[config.measure].keys())]

    def render(self, display):
        with canvas(display) as draw:
            config = self.screen_config[self.screen_index]

            if self.screen_index in (0, 1):
                config.renderer.render(draw,
                                       config,
                                       self.measures,
                                       header_function=self.get_default_header)
            elif self.screen_index == 2:
                config.renderer.render(draw,
                                       config,
                                       self.measures,
                                       count_function=self.count_max)
            elif self.screen_index == 3:
                config.renderer.render(draw,
                                       config,
                                       self.measures,
                                       count_function=self.count_max,
                                       keys_function=self.get_trx_keys)
            elif self.screen_index == 4:
                config.renderer.render(draw,
                                       config,
                                       self.measures,
                                       count_function=self.count_max,
                                       bar_width=16)

    def collect(self):

        sock = None
        last_collect = time.time()
        next_collect = last_collect + self.sleep_interval()

        messages = 0
        planes = set()
        transmission_types = {
            '1': 0,
            '2': 0,
            '3': 0,
            '4': 0,
            '5': 0,
            '6': 0,
            '7': 0,
            '8': 0
        }
        message_types = {
            'SEL': 0,
            'ID': 0,
            'AIR': 0,
            'STA': 0,
            'CLK': 0,
            'MSG': 0
        }
        no_data_errors = 0
        unknown_errors = 0

        while True:
            if sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((self.host, self.port))
                    sock.settimeout(self.socket_timeout)
                except socket.error:
                    # Reset the socket and sleep for a bit, next iteration we'll attempt to connect
                    # again.  We can't simply rely on dump1090-fa being a dependency in the service
                    # script because:
                    # 1. The monitor may not be used with ADS-B monitoring in every case
                    # 2. We my not always be running as a service
                    sock = None
                    time.sleep(1)
            else:
                if time.time() >= next_collect:

                    self.measures['messages'].append(messages)
                    messages = 0

                    self.measures['planes'].append(len(planes))
                    planes = set()

                    self.measures['errors']['no_data'].append(no_data_errors)
                    no_data_errors = 0

                    self.measures['errors']['unknown'].append(unknown_errors)
                    unknown_errors = 0

                    for key, value in transmission_types.items():
                        self.measures['transmission_types'][key].append(transmission_types[key])
                        transmission_types[key] = 0

                    for key in message_types.keys():
                        self.measures['message_types'][key].append(message_types[key])
                        message_types[key] = 0

                    last_collect = time.time()
                    next_collect = last_collect + self.sleep_interval()
                else:
                    try:
                        data = sock.recv(512)
                        messages = messages + 1

                        msg = SBS1Message(data)

                        if msg.tx_type is not None and (msg.tx_type > 0 and msg.tx_type <= 8):
                            transmission_types[str(msg.tx_type)] = transmission_types[str(msg.tx_type)] + 1

                        if msg.message_type is not None and msg.message_type in message_types.keys():
                            message_types[msg.message_type] = message_types[msg.message_type] + 1

                        planes.add(msg.icao24)

                    except socket.error, e:
                        err = e.args[0]
                        
                        if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                            no_data_errors = no_data_errors + 1
                            sock = None
                            time.sleep(0.5)
                        else:
                            unknown_errors = unknown_errors + 1
                            sock = None
                            time.sleep(0.5)
