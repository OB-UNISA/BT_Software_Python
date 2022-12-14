import ipaddress
import json
import os
import socket
import threading

import geoip2.database
import geoip2.errors
import requests


class GeoIP2:
    def __init__(self, path):
        self.reader_city = geoip2.database.Reader(os.path.join(path, 'GeoLite2-City.mmdb'))
        self.not_found_ips = set()

    def get_relevant_data(self, ip):
        try:
            response = self.reader_city.city(ip)
            return {
                'lat': response.location.latitude,
                'lon': response.location.longitude,
                'country': response.country.name,
            }
        except geoip2.errors.AddressNotFoundError:
            self.not_found_ips.add(ip)
            return None


class IPUtils:
    _hostname_cache_file = '.hostname_cache'

    def __init__(self, geoip_path=None, lock=True):
        if lock:
            self._geo_lock_name = 'geo_lock'
            setattr(self, self._geo_lock_name, threading.Lock())
            self.lock(self.get_relevant_geoip_data, self._geo_lock_name)
            self._hostname_lock_name = 'hostname_lock'
            setattr(self, self._hostname_lock_name, threading.Lock())
            self.lock(self.get_hostname_from_ip, self._hostname_lock_name)
        else:
            self._geo_lock = self._hostname_lock = None
        self.geo_ips_known = {}
        self.hostname_ips_known = {}
        self.new_hostnames = 0
        self.new_flagged_hosts = 0

        if geoip_path:
            self.geoip2 = GeoIP2(geoip_path)
        if os.path.exists(self._hostname_cache_file):
            self.load_hostname_cache()
        self.flagged_hosts = self.load_flagged_hosts_list()
        self._local_flagged_hosts_cache = {}

    def get_relevant_geoip_data(self, ip):
        if ip not in self.geo_ips_known:
            self.geo_ips_known[ip] = self.geoip2.get_relevant_data(ip)
        return self.geo_ips_known[ip]

    def get_hostname_from_ip(self, ip):
        if ip not in self.hostname_ips_known:
            try:
                self.hostname_ips_known[ip] = socket.gethostbyaddr(ip)[0]
            except socket.herror:
                self.hostname_ips_known[ip] = None
            self.new_hostnames += 1

        if ip not in self._local_flagged_hosts_cache:
            self._local_flagged_hosts_cache[ip] = self.hostname_ips_known[ip] in self.flagged_hosts
        if self._local_flagged_hosts_cache[ip]:
            self.new_flagged_hosts += 1

        return {'hostname': self.hostname_ips_known[ip], 'flagged': self._local_flagged_hosts_cache[ip]}

    def lock(self, function, locker_name):
        locker = getattr(self, locker_name)

        def wrapper(*args, **kwargs):
            with locker:
                return function(*args, **kwargs)

        return wrapper if locker else function

    def load_hostname_cache(self):
        with open(self._hostname_cache_file, 'r') as f:
            self.hostname_ips_known = json.load(f)

    def save_hostname_cache(self):
        with open(self._hostname_cache_file, 'w') as f:
            json.dump(self.hostname_ips_known, f)

    @staticmethod
    def load_flagged_hosts_list():
        hosts = set()

        # StevenBlack hosts file
        hosts1 = requests.get('https://raw.githubusercontent.com/StevenBlack/hosts/master/data/StevenBlack/hosts').text
        hosts1 = hosts1.split("\n")
        hosts1 = [host for host in hosts1 if host.startswith('0')]
        hosts1 = [host.split()[1] for host in hosts1]
        hosts.update(hosts1)

        # Stamparm hosts file
        hosts2 = requests.get('https://raw.githubusercontent.com/stamparm/aux/master/maltrail-malware-domains.txt').text
        hosts2 = hosts2.split("\n")
        hosts.update(hosts2)
        return hosts


def is_private_ip(ip):
    return ipaddress.ip_address(ip).is_private


def split_dataset_in_chunks(dataset, chunk_size):
    # Using yield would be better to avoid memory issues, but it is not easy to manage with multithreading
    chunks = []
    len_p_data = len(dataset['p_data']) if dataset['p_data'] else 0
    len_n_data = len(dataset['n_data']) if dataset['n_data'] else 0

    for i in range(0, max(len_n_data, len_p_data), chunk_size):
        chunk_dataset = {
            'label': dataset['label'],
            'p_data': dataset['p_data'][i:i + chunk_size] if len_p_data > 0 and i < len_p_data else None,
            'n_data': dataset['n_data'][i:i + chunk_size] if len_n_data > 0 and i < len_n_data else None,
            'p_columns': dataset['p_columns'],
            'n_columns': dataset['n_columns'],
            'p_ts_index': dataset['p_ts_index'],
            'n_ts_index': dataset['n_ts_index'],
            'n_dst_index': dataset['n_dst_index']
        }
        chunks.append(chunk_dataset)
    return chunks
