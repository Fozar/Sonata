import json
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp_cors import CorsViewMixin

from sonata.bot import utils
from sonata.bot.utils.misc import lang_to_locale

if TYPE_CHECKING:
    from sonata.bot import Sonata


class CogList(web.View, CorsViewMixin):
    async def get(self):
        bot: "Sonata" = self.request.app.get("bot")
        bot.locale = "ru_RU"
        return web.json_response(
            text=json.dumps(
                {
                    "data": list(
                        sorted(filter(lambda c: c != "Owner", bot.cogs.keys()))
                    ),
                    "status": 200,
                },
                ensure_ascii=False,
            )
        )


class Cog(web.View, CorsViewMixin):
    async def get(self):
        bot: "Sonata" = self.request.app.get("bot")
        cog_name = self.request.match_info["name"]
        lang = self.request.query.get("lang")
        bot.locale = lang_to_locale(lang) or "en_US"
        cog = bot.get_cog(cog_name)
        if not cog or cog.qualified_name == "Owner":
            return web.Response(status=404, reason="Cog not found")

        return web.json_response(
            text=json.dumps({"data": cog.to_dict(), "status": 200}, ensure_ascii=False)
        )
