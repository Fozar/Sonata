import json
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp_cors import CorsViewMixin

if TYPE_CHECKING:
    from sonata.bot import Sonata


class Cog(web.View, CorsViewMixin):
    async def get(self):
        bot: "Sonata" = self.request.app.get("bot")
        bot.locale = "ru_RU"
        return web.json_response(
            text=json.dumps(
                {
                    "cogs": [
                        c.to_dict()
                        for c in sorted(
                            bot.cogs.values(), key=lambda c: c.qualified_name
                        )
                        if c.qualified_name != "Owner"
                    ]
                },
                ensure_ascii=False,
            )
        )
