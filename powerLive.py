import argparse
import os
import re
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime

import matplotlib.pyplot as plt
import requests
from dotenv import load_dotenv
from matplotlib.animation import FuncAnimation


class Plug(ABC):

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def get_load(self):
        pass

    @abstractmethod
    def turn_on(self):
        pass

    @abstractmethod
    def turn_off(self):
        pass


class ShellyPlugS(Plug):
    def __init__(self, ip):
        self.ip = ip

    @property
    def name(self):
        return 'Shelly Plug S'

    def get_load(self):
        return requests.get(f'http://{self.ip}/meter/0').json()['power']

    def turn_on(self):
        requests.get(f'http://{self.ip}/settings?led_status_disable=false')
        requests.get(f'http://{self.ip}/settings?led_power_disable=false')
        return requests.get(f'http://{self.ip}/relay/0?turn=on').json()['ison']

    def turn_off(self):
        return not requests.get(f'http://{self.ip}/relay/0?turn=off').json()['ison']


class PowerLive:
    def __init__(self, plug: Plug, buffer_length, vertical=True, db_name=None, db_reset=False, verbose=False):
        self.plug = plug
        self.buffer_length = buffer_length
        self.verbose = verbose

        self.db_name = db_name
        if self.db_name:
            self.conn = sqlite3.connect(db_name)
            self.cur = self.conn.cursor()
            try:
                self.cur.execute(
                    'CREATE TABLE plug_load (timestamp TIMESTAMP PRIMARY KEY, power REAL, is_valid BOOLEAN)')
                self.conn.commit()
                print('Created table')
            except sqlite3.OperationalError:
                pass
            if db_reset:
                self.cur.execute('DELETE FROM plug_load')
                self.conn.commit()
                print('Deleted all rows from table')
            self.cur.execute('INSERT INTO plug_load VALUES (?, ?, ?)', (datetime.utcnow(), 0, 0))
            print(f'Data will be saved to {db_name}')

        self.x1 = [0]
        self.y1 = [0]
        self.x2 = [0 for _ in range(self.buffer_length + 1)]
        self.y2 = [0 for _ in range(self.buffer_length + 1)]

        if vertical:
            self.fig, (self.ax1, self.ax2) = plt.subplots(2)
        else:
            self.fig, (self.ax1, self.ax2) = plt.subplots(1, 2)

        self.fig.suptitle(f'{self.plug.name} Power Live [{datetime.utcnow()}] (UTC)')
        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('Power (W)')
        self.ax1.grid()
        self.ax2.set_xlabel(f'Time (s), Buffer Length: {self.buffer_length}s')
        self.ax2.set_ylabel('Power (W)')
        self.ax2.grid()
        self.ln1, = self.ax1.plot([], [], 'g-')
        self.ln2, = self.ax2.plot([], [], 'g-')
        self.ani = FuncAnimation(self.fig, self.update, interval=1000)

        self.plug.turn_on()

        plt.show()

    def update(self, frame):
        data = {'timestamp': datetime.utcnow(), 'power': self.plug.get_load(), 'is_valid': 1}
        if self.verbose:
            print(data)
        self.update_full_graph(data)
        self.update_buffer_graph(data)
        if self.db_name:
            self.send_to_sql(data)

        return self.ln1, self.ln2

    def update_full_graph(self, data):
        self.x1.append(self.x1[-1] + 1)
        self.y1.append(data['power'])
        self.update_set_data(self.ax1, self.ln1, self.x1, self.y1)

    # A better solution would be to use the original data in x1 and y1 and pass to the buffer only the indexes.
    # But it seems it can not be done in Python. If you use Slice operator, it will create a copy of the list arr[a:b]
    # from index a to b which means at every interval a list of length b-a will be created. The current solution only
    # requires 2 operations on the list and additional space for the list, compared to the Slice which would requires
    # b-a operations.
    def update_buffer_graph(self, data):
        self.x2.pop(0)
        self.x2.append(self.x2[-1] + 1)
        self.y2.pop(0)
        self.y2.append(data['power'])
        self.update_set_data(self.ax2, self.ln2, self.x2, self.y2)

    @staticmethod
    def update_set_data(ax, ln, x, y):
        ln.set_data(x, y)
        ax.relim()
        ax.autoscale_view()

    def send_to_sql(self, data):
        self.cur.execute('INSERT INTO plug_load VALUES (?, ?, ?)',
                         (data['timestamp'], data['power'], data['is_valid']))
        self.conn.commit()

    def __del__(self):
        if self.db_name:
            self.conn.close()


if __name__ == '__main__':
    def buffer_length_type(value):
        ivalue = int(value)
        if ivalue < 2:
            raise argparse.ArgumentTypeError(f'{value} is an invalid positive int value, must be >= 2')

        return ivalue


    def ip_type(value):
        if not re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value):
            raise argparse.ArgumentTypeError(f'{value} is an invalid IP address')

        return value


    load_dotenv()

    parser = argparse.ArgumentParser('Plug Power Live')
    parser.add_argument('-ip', type=ip_type, default=os.getenv('PLUG_IP'), help='Plug IP')
    parser.add_argument('-b', '--buffer_length', type=buffer_length_type, default=30,
                        help='buffer length in seconds, must be a positive int value >= 2. Default is 30')
    parser.add_argument('-hr', '--horizontal', action='store_true', help='horizontal layout, default is vertical')
    parser.add_argument('-db', default=os.getenv('DB_NAME'), help='SQLite DB name')
    parser.add_argument('--db_reset', action='store_true', help='reset SQLite DB')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='verbose mode, print data to console. Default is False')
    args = parser.parse_args()

    if not args.ip:
        exit('IP is not set, please set it in .env file or pass it as argument')

    shelly_plug = ShellyPlugS(args.ip)
    PowerLive(shelly_plug, args.buffer_length, vertical=not args.horizontal, db_name=args.db, db_reset=args.db_reset,
              verbose=args.verbose)