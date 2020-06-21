import json

import discord
from aiohttp import web
from aiohttp_security import check_authorized

from sonata.views.view import View


class UserMe(View):
    async def get(self):
        try:
            user_id = int(await check_authorized(self.request))
        except TypeError:
            raise web.HTTPBadRequest
        user = await self.bot.db.users.find_one(
            {"id": user_id}, {"_id": False, "created_at": False}
        )
        if not user:
            raise web.HTTPNotFound

        guilds = []
        for guild_id in user["guilds"]:
            try:
                guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            except discord.HTTPException:
                continue
            else:
                guild_name = guild.name
                is_owner = await self.bot.is_admin(member)
            guilds.append({"id": guild_id, "name": guild_name, "is_owner": is_owner})
        user["guilds"] = guilds

        return web.json_response(text=json.dumps(user, ensure_ascii=False))
