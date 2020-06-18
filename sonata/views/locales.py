import json

from aiohttp import web
from aiohttp_cors import CorsViewMixin

from sonata.bot.utils.misc import map_locale


class Locales(web.View, CorsViewMixin):
    async def get(self):
        return web.json_response(text=json.dumps(map_locale(), ensure_ascii=False))
