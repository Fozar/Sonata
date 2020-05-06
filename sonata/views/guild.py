from aiohttp import web
from aiohttp_cors import CorsViewMixin


class Guild(web.View, CorsViewMixin):
    async def get(self):
        bot = self.request.app.get("bot")
        guilds = len(bot.guilds) if bot else 0
        members = len(bot.users) if bot else 0
        return web.json_response({"guilds": guilds, "members": members})
