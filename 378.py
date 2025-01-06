"""
A new Python wrapper for interacting with the Open311 API.
"""

import os
import re
from collections import defaultdict
from datetime import date


import requests
from relaxml import xml
import simplejson as json

try:
    # Python 2
    from future_builtins import filter
except ImportError:
    # Python 3
    pass


class SSLAdapter(requests.adapters.HTTPAdapter):
    """An HTTPS Transport Adapter that uses an arbitrary SSL version."""
    def __init__(self, ssl_version=None, **kwargs):
        self.ssl_version = ssl_version
        super(SSLAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block):
        self.poolmanager = requests.packages.urllib3.poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_version=self.ssl_version)


class Three(object):
    """The main class for interacting with the Open311 API."""

    def __init__(self, endpoint=None, **kwargs):
        keywords = defaultdict(str)
        keywords.update(kwargs)
        if endpoint:
            endpoint = self._configure_endpoint(endpoint)
            keywords['endpoint'] = endpoint
        elif 'OPEN311_CITY_INFO' in os.environ:
            info = json.loads(os.environ['OPEN311_CITY_INFO'])
            endpoint = info['endpoint']
            endpoint = self._configure_endpoint(endpoint)
            keywords.update(info)
            keywords['endpoint'] = endpoint
        self._keywords = keywords
        self.configure()

    def _global_api_key(self):
        """
        If a global Open311 API key is available as an environment variable,
        then it will be used when querying.
        """
        if 'OPEN311_API_KEY' in os.environ:
            api_key = os.environ['OPEN311_API_KEY']
        else:
            api_key = ''
        return api_key

    def configure(self, endpoint=None, **kwargs):
        """Configure a previously initialized instance of the class."""
        if endpoint:
            kwargs['endpoint'] = endpoint
        keywords = self._keywords.copy()
        keywords.update(kwargs)
        if 'endpoint' in kwargs:
            # Then we need to correctly format the endpoint.
            endpoint = kwargs['endpoint']
            keywords['endpoint'] = self._configure_endpoint(endpoint)
        self.api_key = keywords['api_key'] or self._global_api_key()
        self.endpoint = keywords['endpoint']
        self.format = keywords['format'] or 'json'
        self.jurisdiction = keywords['jurisdiction']
        self.proxy = keywords['proxy']
        self.discovery_url = keywords['discovery'] or None

        # Use a custom requests session and set the correct SSL version if
        # specified.
        self.session = requests.Session()
        if 'ssl_version' in keywords:
            self.session.mount('https://', SSLAdapter(keywords['ssl_version']))

    def _configure_endpoint(self, endpoint):
        """Configure the endpoint with a schema and end slash."""
        if not endpoint.startswith('http'):
            endpoint = 'https://' + endpoint
        if not endpoint.endswith('/'):
            endpoint += '/'
        return endpoint

    def reset(self):
        """Reset the class back to the original keywords and values."""
        self.configure()

    def _create_path(self, *args):
        """Create URL path for endpoint and args."""
        args = filter(None, args)
        path = self.endpoint + '/'.join(args) + '.%s' % (self.format)
        return path

    def get(self, *args, **kwargs):
        """Perform a get request."""
        if 'convert' in kwargs:
            conversion = kwargs.pop('convert')
        else:
            conversion = True
        kwargs = self._get_keywords(**kwargs)
        url = self._create_path(*args)
        request = self.session.get(url, params=kwargs)
        content = request.content
        self._request = request
        return self.convert(content, conversion)

    def _get_keywords(self, **kwargs):
        """Format GET request parameters and keywords."""
        if self.jurisdiction and 'jurisdiction_id' not in kwargs:
            kwargs['jurisdiction_id'] = self.jurisdiction
        if 'count' in kwargs:
            kwargs['page_size'] = kwargs.pop('count')
        if 'start' in kwargs:
            start = kwargs.pop('start')
            if 'end' in kwargs:
                end = kwargs.pop('end')
            else:
                end = date.today().strftime('%m-%d-%Y')
            start, end = self._format_dates(start, end)
            kwargs['start_date'] = start
            kwargs['end_date'] = end
        elif 'between' in kwargs:
            start, end = kwargs.pop('between')
            start, end = self._format_dates(start, end)
            kwargs['start_date'] = start
            kwargs['end_date'] = end
        return kwargs

    def _format_dates(self, start, end):
        """Format start and end dates."""
        start = self._split_date(start)
        end = self._split_date(end)
        return start, end

    def _split_date(self, time):
        """Split apart a date string."""
        if isinstance(time, str):
            month, day, year = [int(t) for t in re.split(r'-|/', time)]
            if year < 100:
                # Quick hack for dates < 2000.
                year += 2000
            time = date(year, month, day)
        return time.strftime('%Y-%m-%dT%H:%M:%SZ')

    def convert(self, content, conversion):
        """Convert content to Python data structures."""
        if not conversion:
            data = content
        elif self.format == 'json':
            data = json.loads(content)
        elif self.format == 'xml':
            content = xml(content)
            first = list(content.keys())[0]
            data = content[first]
        else:
            data = content
        return data

    def discovery(self, url=None):
        """
        Retrieve the standard discovery file that provides routing
        information.

        >>> Three().discovery()
        {'discovery': 'data'}
        """
        if url:
            data = self.session.get(url).content
        elif self.discovery_url:
            response = self.session.get(self.discovery_url)
            if self.format == 'xml':
                # Because, SF doesn't follow the spec.
                data = xml(response.text)
            else:
                # Spec calls for discovery always allowing JSON.
                data = response.json()
        else:
            data = self.get('discovery')
        return data

    def services(self, code=None, **kwargs):
        """
        Retrieve information about available services. You can also enter a
        specific service code argument.

        >>> Three().services()
        {'all': {'service_code': 'data'}}
        >>> Three().services('033')
        {'033': {'service_code': 'data'}}
        """
        data = self.get('services', code, **kwargs)
        return data

    def requests(self, code=None, **kwargs):
        """
        Retrieve open requests. You can also enter a specific service code
        argument.

        >>> Three('api.city.gov').requests()
        {'all': {'requests': 'data'}}
        >>> Three('api.city.gov').requests('123')
        {'123': {'requests': 'data'}}
        """
        if code:
            kwargs['service_code'] = code
        data = self.get('requests', **kwargs)
        return data

    def request(self, id, **kwargs):
        """
        Retrieve a specific request using its service code ID.

        >>> Three('api.city.gov').request('12345')
        {'request': {'service_code': {'12345': 'data'}}}
        """
        data = self.get('requests', id, **kwargs)
        return data

    def post(self, service_code='0', **kwargs):
        """
        Post a new Open311 request.

        >>> t = Three('api.city.gov')
        >>> t.post('123', address='123 Any St', name='Zach Williams',
        ...        phone='555-5555', description='My issue description.',
        ...        media=open('photo.png', 'rb'))
        {'successful': {'request': 'post'}}
        """
        kwargs['service_code'] = service_code
        kwargs = self._post_keywords(**kwargs)
        media = kwargs.pop('media', None)
        if media:
            files = {'media': media}
        else:
            files = None
        url = self._create_path('requests')
        self.post_response = self.session.post(url,
                                               data=kwargs, files=files)
        content = self.post_response.content
        if self.post_response.status_code >= 500:
            conversion = False
        else:
            conversion = True
        return self.convert(content, conversion)

    def _post_keywords(self, **kwargs):
        """Configure keyword arguments for Open311 POST requests."""
        if self.jurisdiction and 'jurisdiction_id' not in kwargs:
            kwargs['jurisdiction_id'] = self.jurisdiction
        if 'address' in kwargs:
            address = kwargs.pop('address')
            kwargs['address_string'] = address
        if 'name' in kwargs:
            first, last = kwargs.pop('name').split(' ')
            kwargs['first_name'] = first
            kwargs['last_name'] = last
        if 'api_key' not in kwargs:
            kwargs['api_key'] = self.api_key
        return kwargs

    def token(self, id, **kwargs):
        """
        Retrieve a service request ID from a token.

        >>> Three('api.city.gov').token('12345')
        {'service_request_id': {'for': {'token': '12345'}}}
        """
        data = self.get('tokens', id, **kwargs)
        return data
