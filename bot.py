# coding: utf-8

import asyncio
import json
import re
from datetime import datetime
from urllib import parse

import aiohttp
import asyncio_redis
import telepot
import telepot.aio
from telepot.namedtuple import ReplyKeyboardMarkup, ReplyKeyboardRemove

from constants import GAME_CARD_TEMPLATE, NEWS_CARD_TEMPLATE, LANG, CC
from utils import SearchSuggestParser, cache_steam_response, group


class SteamBot(telepot.aio.Bot, telepot.helper.AnswererMixin):

    def __init__(self, *args, config=None, **kwargs):
        super(SteamBot, self).__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)
        self.config = config
        self.cache_time = self.config.get('cache_time', 10)
        self.redis_conn = None
        self.loop.create_task(self.initialize_redis())
        self.routes = {
            '/search': self.search_game,
            '/app_': self.game_card_answer,
            '/scr_': self.screenshots_answer,
            '/news_': self.last_news_answer,
            '/feedback': self.feedback_answer,
            '/settings': self.settings_answer,
            '/lang': self.set_lang,
            '/cc': self.set_cc,
            '/start': self.welcome_answer
        }

    async def initialize_redis(self):
        self.redis_conn = await asyncio_redis.Pool.create(
            host=self.config['redis']['ip'],
            port=self.config['redis']['port'],
            db=self.config['redis']['db'],
            poolsize=5
        )

    @cache_steam_response
    async def get_content_from_url(self, url, resp_format=None):
        async with aiohttp.ClientSession(loop=self.loop) as client:
            async with client.get(url) as resp:
                if resp.status != 200:
                    return
                if resp_format == 'text':
                    result = await resp.text()
                elif resp_format == 'json':
                    result = await resp.json()
                else:
                    result = await resp.content.read()
                return result

    async def get_search_results(self, term, settings):
        search_url = u'https://store.steampowered.com/search/suggest?term={}&f=games&l={}&cc={}'.format(
            parse.quote_plus(term),
            settings.get('lang'),
            settings.get('cc')
        )
        content = await self.get_content_from_url(search_url, resp_format='text')
        parser = SearchSuggestParser()
        parser.feed(content)
        return parser.result

    async def get_appdetails(self, appid, settings={}):
        url = u'https://store.steampowered.com/api/appdetails/?appids={}&l={}&cc={}'.format(
            appid,
            settings.get('lang'),
            settings.get('cc')
        )
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
                    return msg['text'][offset:length], msg['text'][offset + length:].strip()
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
            platforms=', '.join(
                [x[0] for x in appdetails['platforms'].items() if x[1]]),
            genres=', '.join(
                [x['description'] for x in appdetails['genres']]) if 'genres' in appdetails else '',
            publishers=', '.join(
                appdetails['publishers']) if 'publishers' in appdetails else '',
            price='{} {}'.format(appdetails['price_overview']['final'] / 100.0,
                                 appdetails['price_overview']['currency']) if 'price_overview' in appdetails else '',
            recommendations=appdetails['recommendations']['total'] if 'recommendations' in appdetails else '',
            screenshotscount=len(
                appdetails['screenshots']) if 'screenshots' in appdetails else '0',
            about_the_game=self.clean_html(appdetails['about_the_game'])[:500]
        )

    async def on_callback_query(self, msg):
        query_id, from_id, data = telepot.glance(msg, flavor='callback_query')
        print('Callback query:', query_id, from_id, data)
        self.route(from_id, data)

    async def game_search_answer(self, term, chat_id):
        user_info = await self.get_user(chat_id)
        settings = user_info.get('settings')
        msg = self.get_games_message(await self.get_search_results(term, settings))
        await self.sendMessage(chat_id, msg, parse_mode='markdown', disable_web_page_preview=True)

    async def game_card_answer(self, chat_id, command, args):
        appid = command.replace('/app_', '').strip()
        self.loop.create_task(self.sendChatAction(chat_id, 'typing'))
        user_info = await self.get_user(chat_id)
        settings = user_info.get('settings')
        app_details = await self.get_appdetails(appid, settings)
        await self.sendMessage(chat_id, self.get_game_card_message(app_details), parse_mode='markdown')

    async def send_photo_from_url(self, url, photo_name, chat_id):
        downloaded_file = await self.get_content_from_url(url)
        await self.sendPhoto(chat_id, photo=(photo_name, downloaded_file))

    async def screenshots_answer(self, chat_id, command, args):
        appid = command.replace('/scr_', '').strip()
        self.loop.create_task(self.sendChatAction(chat_id, 'upload_photo'))
        app_details = await self.get_appdetails(appid)
        for scr in app_details['screenshots']:
            loop.create_task(self.send_photo_from_url(
                scr['path_full'], 'scr-{}.jpg'.format(scr['id']), chat_id))

    async def last_news_answer(self, chat_id, command, args):
        appid = command.replace('/news_', '').strip()
        self.loop.create_task(self.sendChatAction(chat_id, 'typing'))
        news_items = await self.get_news(appid)
        for item in news_items:
            msg = NEWS_CARD_TEMPLATE.format(
                title=item['title'],
                url=item['url'],
                pub_date=datetime.fromtimestamp(
                    int(item['date'])).strftime("%B %d, %Y"),
                feedlabel=item['feedlabel'],
                contents=self.clean_markdown(self.clean_html(item['contents'])).replace(
                    '\n', '').replace('  ', '')[:300],
                author=item['author']
            )
            loop.create_task(self.sendMessage(
                chat_id, msg, parse_mode='markdown'))

    def get_user_key(self, user_id):
        return 'user-{}'.format(user_id)

    async def save_user_settings(self, user_id, new_settings):
        key = self.get_user_key(user_id)
        user = await self.get_user(user_id)
        settings = user.get('settings', {})
        settings.update(new_settings)
        user['settings'] = settings
        await self.redis_conn.set(key, json.dumps(user))

    async def get_user(self, user_id):
        return json.loads(await self.redis_conn.get(self.get_user_key(user_id)))

    async def create_or_update_user(self, chat):
        key = self.get_user_key(chat['id'])
        user = await self.redis_conn.get(key)
        if not user:
            new_user = chat
            default_settings = {
                'lang': 'english',
                'cc': 'US'
            }
            new_user_serialized = json.dumps(
                {'info': new_user, 'settings': default_settings})
            await self.redis_conn.set(key, new_user_serialized)
        else:
            user = json.loads(user)
            if chat != user['info']:
                user['info'] = chat
                await self.redis_conn.set(key, json.dumps(user))

    async def on_inline_query(self, msg):
        async def compute_answer():
            query_id, from_id, query_string = telepot.glance(
                msg, flavor='inline_query')
            print('inline query: {} from_id: {}'.format(query_string, from_id))
            user_info = await self.get_user(from_id)
            settings = user_info.get('settings')
            results = await self.get_search_results(query_string, settings)
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
                    # 'url': res['href'],
                    'description': res['price'],
                    'thumb_url': res['image']
                })
            return {'results': articles}
        self._answerer.answer(msg, compute_answer)

    async def on_chosen_inline_result(self, msg):
        query_id, from_id, query_string = telepot.glance(
            msg, flavor='chosen_inline_result')
        print('Chosen Inline Result: {} {} from_id: {}'.format(
            query_id, query_string, from_id))
        await self.game_card_answer(query_id, from_id)

    async def search_game(self, chat_id, command, args):
        await self.sendChatAction(chat_id, 'typing')
        await self.game_search_answer(args, chat_id)

    async def set_lang(self, chat_id, command, args):
        lang = args.strip() if args else None
        if lang:
            await self.save_user_settings(chat_id, {'lang': LANG.get(lang)})
            await bot.sendMessage(chat_id, 'language saved', reply_markup=ReplyKeyboardRemove())
        else:
            markup = ReplyKeyboardMarkup(
                keyboard=group(['/lang' + x for x in LANG.keys()], 2),
                one_time_keyboard=True
            )
            await bot.sendMessage(chat_id, 'set language', reply_markup=markup)

    async def set_cc(self, chat_id, command, args):
        cc = args.strip() if args else None
        if cc:
            await self.save_user_settings(chat_id, {'cc': CC.get(cc)})
            await bot.sendMessage(chat_id, 'region saved', reply_markup=ReplyKeyboardRemove())
        else:
            markup = ReplyKeyboardMarkup(
                keyboard=group(['/cc' + x for x in CC.keys()], 3),
                one_time_keyboard=True
            )
            await bot.sendMessage(chat_id, 'set region', reply_markup=markup)

    async def feedback_answer(self, chat_id, command, args):
        msg = args.replace('/feedback ', '').strip()
        if msg:
            await self.sendMessage(
                self.config.get('admin_id'),
                'feedback from: {}: {}'.format(chat_id, msg)
            )
            await self.sendMessage(chat_id, 'thank you for your feedback!')
        else:
            await self.sendMessage(chat_id, 'looks like your feedback is empty!')

    async def settings_answer(self, chat_id, command, args):
        await self.sendMessage(
            chat_id,
            "change region: /cc\n"
            "change language: /lang\n"
        )

    async def welcome_answer(self, chat_id, command, args):
        await self.sendMessage(
            chat_id,
            'Welcome! Just type / for view list of commands, also you can use this bot with inline mode.\n'
            'For search a game just send message with game title'
        )

    def route(self, chat_id, command, args=None):
        func = None
        for cmd, fnc in self.routes.items():
            if command.find(cmd) != -1:
                func = fnc
                break

        if func:
            self.loop.create_task(func(chat_id, command, args))

    async def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)
        print(msg)
        await self.create_or_update_user(msg.get('chat'))
        command, args = self.get_command(msg)
        if not command:
            command, args = '/search', msg['text']
        self.route(chat_id, command, args)


with open('conf/config.json') as f:
    config = json.loads(f.read())

loop = asyncio.get_event_loop()
token = config.pop("telegram_token")
bot = SteamBot(token=token, config=config, loop=loop)
loop.create_task(bot.message_loop())
print('Listening ...')
loop.run_forever()
