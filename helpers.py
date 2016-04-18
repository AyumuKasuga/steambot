# coding: utf-8
from html.parser import HTMLParser


class SearchSuggestParser(HTMLParser):

    def __init__(self):
        super(SearchSuggestParser, self).__init__()
        self.result = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('data-ds-appid') and attrs.get('href'):
            self.result.append({})
            self.result[-1]['appid'] = attrs['data-ds-appid']
            self.result[-1]['href'] = attrs['href']
        elif tag == 'div' and attrs.get('class') == 'match_name':
            self.result[-1]['name'] = u''
        elif tag == 'img' and attrs.get('src'):
            self.result[-1]['image'] = attrs['src']
        elif tag == 'div' and attrs.get('class') == 'match_price':
            self.result[-1]['price'] = u''

    def handle_data(self, data):
        if self.result[-1].get('name') == u'':
            self.result[-1]['name'] = data
        elif self.result[-1].get('price') == u'':
            self.result[-1]['price'] = data
