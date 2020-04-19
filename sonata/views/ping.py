from aiohttp import web


class Ping(web.View):
    async def get(self):
        bot = self.request.app.get("bot")
        if bot:
            guilds = ", ".join(g.name for g in bot.guilds)
        else:
            guilds = "<None>"

        return web.Response(text=f"Pong! I am connected to {len(guilds)} guilds.")
