# coding: utf-8

import asyncio
import aiohttp
import telepot
import telepot.async
import re
from datetime import datetime
import asyncio_redis
from hashlib import md5
import json

from helpers import SearchSuggestParser


GAME_CARD_TEMPLATE = """
*{name} ({release_date})* [steam](https://store.steampowered.com/app/{appid}/)
{metacritic}
*platforms:* _{platforms}_
*genres:* _{genres}_
*publisher:* _{publishers}_
*recommendations:* _{recommendations}_
*price:* _{price}_
_get {screenshotscount} screenshots:_ /scr\_{appid}
_get last news:_ /news\_{appid}


{about_the_game}
"""

NEWS_CARD_TEMPLATE = """
*{title}* [read on site]({url})
_{pub_date}_
_{feedlabel}_

{contents}

_{author}_
"""


class SteamBot(telepot.async.Bot):

    def __init__(self, *args, config=None, **kwargs):
        super(SteamBot, self).__init__(*args, **kwargs)
        self._answerer = telepot.async.helper.Answerer(self)
        self.config = config
        self.cache_time = self.config.get('cache_time', 300)
        self.redis_conn = None
        self.loop.create_task(self.initialize_redis())

    async def initialize_redis(self):
        self.redis_conn = await asyncio_redis.Pool.create(
            host=self.config['redis']['ip'],
            port=self.config['redis']['port'],
            db=self.config['redis']['db'],
            poolsize=5
        )

    async def get_content_from_url(self, url, resp_format=None):
        cache_key = 'cached-response-{}'.format(md5(url.encode('utf-8')).hexdigest())
        if resp_format:
            cached_data = await self.redis_conn.get(cache_key)
            if cached_data:
                if resp_format == 'json':
                    return json.loads(cached_data)
                return cached_data
        with aiohttp.ClientSession(loop=self.loop) as client:
            resp = await client.get(url)
            assert resp.status == 200
            if resp_format == 'text':
                result = await resp.text()
            elif resp_format == 'json':
                result = await resp.json()
            else:
                result = await resp.content.read()
            resp.close()

            if resp_format:
                if resp_format == 'json':
                    to_cache = json.dumps(result)
                else:
                    to_cache = result
                self.loop.create_task(self.redis_conn.set(cache_key, to_cache, self.cache_time))
            return result

    async def get_search_results(self, term):
        search_url = u'https://store.steampowered.com/search/suggest?term={term}&f=games&cc=RU&l=english'.format(
            term=term
        )
        content = self.get_content_from_url(search_url, resp_format='text')
        parser = SearchSuggestParser()
        parser.feed(await content)
        return parser.result

    async def get_appdetails(self, appid):
        url = u'https://store.steampowered.com/api/appdetails/?appids={}'.format(appid)
        content = await self.get_content_from_url(url, resp_format='json')
        return content[appid]['data'] if content else {}

    async def get_news(self, appid, count=3):
        url = u'https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid={}&count={}&max_length=300&format=json'.format(
            appid,
            count
        )
        content = await self.get_content_from_url(url, resp_format='json')
        return content['appnews']['newsitems'] if content else {}

    @staticmethod
    def get_command(msg):
        if 'entities' in msg:
            for entity in msg['entities']:
                if entity['type'] == 'bot_command':
                    offset, length = entity['offset'], entity['length']
                    return msg['text'][offset:length], msg['text'][offset+length:].strip()
        return None, None

    @staticmethod
    def get_games_message(entries):
        msg_list = []
        if len(entries) != 0:
            for entry in entries:
                msg = u"{cmd} {name} [steam]({href}) _{price}_".format(
                    name=entry['name'],
                    href=entry['href'],
                    price=entry['price'],
                    cmd=u'/app\_{}'.format(entry['appid'])
                )
                msg_list.append(msg)
            return u'\n'.join(msg_list)
        return u'Nothing found'

    @staticmethod
    def clean_html(html):
        return re.sub('<[^<]+?>', '', html)

    @staticmethod
    def clean_markdown(text):
        return text.replace('_', '\_').replace('*', '\*')

    def get_game_card_message(self, appdetails):
        return GAME_CARD_TEMPLATE.format(
            appid=appdetails['steam_appid'],
            name=appdetails['name'],
            release_date=appdetails['release_date']['date'],
            metacritic=u'\u2b50\ufe0f{} [metacritics]({})'.format(
                appdetails['metacritic']['score'],
                appdetails['metacritic']['url']
            ) if 'metacritic' in appdetails else '',
            platforms=', '.join([x[0] for x in appdetails['platforms'].items() if x[1]]),
            genres=', '.join([x['description'] for x in appdetails['genres']]) if 'genres' in appdetails else '',
            publishers=', '.join(appdetails['publishers']) if 'publishers' in appdetails else '',
            price='{} {}'.format(appdetails['price_overview']['final']/100.0, appdetails['price_overview']['currency']) if 'price_overview' in appdetails else '',
            recommendations=appdetails['recommendations']['total'] if 'recommendations' in appdetails else '',
            screenshotscount=len(appdetails['screenshots']) if 'screenshots' in appdetails else '0',
            about_the_game=self.clean_html(appdetails['about_the_game'])[:500]
        )

    async def game_search_answer(self, term, chat_id):
        msg = self.get_games_message(await self.get_search_results(term))
        await self.sendMessage(chat_id, msg, parse_mode='markdown', disable_web_page_preview=True)

    async def game_card_answer(self, appid, chat_id):
        app_details = await self.get_appdetails(appid)
        await self.sendMessage(chat_id, self.get_game_card_message(app_details), parse_mode='markdown')

    async def send_photo_from_url(self, url, photo_name, chat_id):
        downloaded_file = await self.get_content_from_url(url)
        await self.sendPhoto(chat_id, photo=(photo_name, downloaded_file))

    async def screenshots_answer(self, appid, chat_id):
        app_details = await self.get_appdetails(appid)
        for scr in app_details['screenshots']:
            loop.create_task(self.send_photo_from_url(scr['path_full'], 'scr-{}.jpg'.format(scr['id']), chat_id))

    async def last_news_answer(self, appid, chat_id):
        news_items = await self.get_news(appid)
        for item in news_items:
            msg = NEWS_CARD_TEMPLATE.format(
                title=item['title'],
                url=item['url'],
                pub_date=datetime.fromtimestamp(int(item['date'])).strftime("%B %d, %Y"),
                feedlabel=item['feedlabel'],
                contents=self.clean_markdown(self.clean_html(item['contents'])).replace('\n', '').replace('  ', '')[:300],
                author=item['author']
            )
            loop.create_task(self.sendMessage(chat_id, msg, parse_mode='markdown'))

    async def on_inline_query(self, msg):
        async def compute_answer():
            query_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
            print('inline query: {} from_id: {}'.format(query_string, from_id))
            results = await self.get_search_results(query_string)
            articles = []
            for res in results:
                articles.append({
                    'type': 'article',
                    'id': res['appid'],
                    'title': res['name'],
                    'message_text': u'{} {} {}'.format(
                        res['name'],
                        res['price'],
                        res['href']
                    ),
                    'url': res['href'],
                    'description': res['price'],
                    'thumb_url': res['image']
                })
            return articles
        self._answerer.answer(msg, compute_answer)

    def search_game(self, term, chat_id):
        self.loop.create_task(self.sendChatAction(chat_id, 'typing'))
        self.loop.create_task(self.game_search_answer(term, chat_id))

    async def on_chat_message(self, msg):
        print(msg)
        content_type, chat_type, chat_id = telepot.glance(msg)
        command, args = self.get_command(msg)
        if command:
            if command == '/search':
                self.search_game(args, chat_id)
            elif command.find('/app_') != -1:
                appid = command.replace('/app_', '').strip()
                self.loop.create_task(self.sendChatAction(chat_id, 'typing'))
                self.loop.create_task(self.game_card_answer(appid, chat_id))
            elif command.find('/scr_') != -1:
                appid = command.replace('/scr_', '').strip()
                self.loop.create_task(self.sendChatAction(chat_id, 'upload_photo'))
                self.loop.create_task(self.screenshots_answer(appid, chat_id))
            elif command.find('/news_') != -1:
                appid = command.replace('/news_', '').strip()
                self.loop.create_task(self.sendChatAction(chat_id, 'typing'))
                self.loop.create_task(self.last_news_answer(appid, chat_id))
        else:
            self.search_game(msg['text'], chat_id)


with open('config.json') as f:
    config = json.loads(f.read())

loop = asyncio.get_event_loop()
token = config.pop("telegram_token")
bot = SteamBot(token=token, config=config, loop=loop)
loop.create_task(bot.messageLoop())
print('Listening ...')
loop.run_forever()
