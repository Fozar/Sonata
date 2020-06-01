import json
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp_cors import CorsViewMixin

if TYPE_CHECKING:
    from sonata.bot import Sonata


class Command(web.View, CorsViewMixin):
    async def get(self):
        bot: "Sonata" = self.request.app.get("bot")
        bot.locale = "ru_RU"
        return web.json_response(
            text=json.dumps(
                {
                    "commands": [
                        c.to_dict()
                        for c in sorted(bot.commands, key=lambda c: c.name)
                        if c.enabled and not c.hidden and c.cog_name != "Owner"
                    ]
                },
                ensure_ascii=False,
            )
        )
