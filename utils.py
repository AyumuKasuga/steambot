# coding: utf-8
import json
from hashlib import md5
from html.parser import HTMLParser


class SearchSuggestParser(HTMLParser):

    def __init__(self):
        super(SearchSuggestParser, self).__init__()
        self.result = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.result.append({})
            self.result[-1]['appid'] = attrs.get('data-ds-appid')
            self.result[-1]['href'] = attrs['href']
        elif tag == 'div' and attrs.get('class') == 'match_name':
            self.result[-1]['name'] = u''
        elif tag == 'img' and attrs.get('src'):
            self.result[-1]['image'] = attrs['src']
        elif tag == 'div' and attrs.get('class') == 'match_price':
            self.result[-1]['price'] = u''

    def handle_data(self, data):
        if len(self.result) == 0:
            return
        if self.result[-1].get('name') == u'':
            self.result[-1]['name'] = data
        elif self.result[-1].get('price') == u'':
            self.result[-1]['price'] = data


def cache_steam_response(func):
    async def wrapper(*args, **kwargs):
        self, url, resp_format = args[0], args[1], kwargs['resp_format']
        if resp_format is None:
            return await func(*args, **kwargs)
        cache_key = 'cached-response-{}'.format(md5(url.encode('utf-8')).hexdigest())
        cached_data = await self.redis_conn.get(cache_key)
        if cached_data:
            if resp_format == 'json':
                return json.loads(cached_data)
            return cached_data
        else:
            result = await func(*args, **kwargs)
            if result is None:
                return
            elif resp_format == 'json':
                to_cache = json.dumps(result)
            else:
                to_cache = result
            self.loop.create_task(self.redis_conn.set(cache_key, to_cache, self.cache_time))
            return result
    return wrapper

group = lambda flat, size: [flat[i:i+size] for i in range(0, len(flat), size)]