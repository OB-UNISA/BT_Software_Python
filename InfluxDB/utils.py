import os

import geoip2.database
import geoip2.errors


class GeoIP2:
    def __init__(self, path):
        self.reader = geoip2.database.Reader(os.path.join(path, 'GeoLite2-City.mmdb'))
        self.not_found_ips = set()

    def get_relevant_data(self, ip):
        try:
            response = self.reader.city(ip)
            return {
                'lat': response.location.latitude,
                'lon': response.location.longitude
            }
        except geoip2.errors.AddressNotFoundError:
            self.not_found_ips.add(ip)
            return None