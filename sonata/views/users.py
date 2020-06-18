import json

import discord
from aiohttp import web
from aiohttp_cors import CorsViewMixin
from aiohttp_security import check_authorized


class UserMe(web.View, CorsViewMixin):
    async def get(self):
        try:
            user_id = int(await check_authorized(self.request))
        except TypeError:
            raise web.HTTPBadRequest
        bot = self.request.app.get("bot")
        user = await bot.db.users.find_one(
            {"id": user_id}, {"_id": False, "created_at": False}
        )
        if not user:
            raise web.HTTPNotFound

        guilds = []
        for guild_id in user["guilds"]:
            guild = await bot.db.guilds.find_one(
                {"id": guild_id}, {"_id": False, "name": True, "owner_id": True}
            )
            if not guild:
                try:
                    guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
                except discord.HTTPException:
                    continue
                else:
                    guild_name = guild.name
                    is_owner = user_id == guild.owner_id
            else:
                guild_name = guild["name"]
                is_owner = user_id == guild["owner_id"]
            guilds.append({"id": guild_id, "name": guild_name, "is_owner": is_owner})
        user["guilds"] = guilds

        return web.json_response(text=json.dumps(user, ensure_ascii=False))
