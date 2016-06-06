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


LANG = {
    '\U0001f1fa\U0001f1f8 English': 'english',
    '\U0001f1f7\U0001f1fa Русский': 'russian',
    '\U0001f1ee\U0001f1f9 Italiano': 'italian'
}

CC = {
    '\U0001f1fa\U0001f1f8': 'US',
    '\U0001f1ec\U0001f1e7': 'GB',
    '\U0001f1e9\U0001f1ea': 'DE',
    '\U0001f1f7\U0001f1fa': 'RU',
    '\U0001f1ee\U0001f1f9': 'IT',
}