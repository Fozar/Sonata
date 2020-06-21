import datetime as dt
import json
import time
from typing import Union

import discord
from aiohttp import web
from aiohttp_security import check_authorized

from .view import View


def date_converter(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return int(time.mktime(o.timetuple()))


class Guilds(View):
    async def get(self):
        return web.json_response(
            {"guilds": len(self.bot.guilds), "members": len(self.bot.users)}
        )


class GuildBase(View):
    async def check_perms(self):
        try:
            user_id = int(await check_authorized(self.request))
            guild_id = int(self.request.match_info["id"])
        except TypeError:
            raise web.HTTPBadRequest
        try:
            guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
            user = guild.get_member(user_id) or await guild.fetch_member(user_id)
        except discord.Forbidden:
            raise web.HTTPForbidden
        except discord.HTTPException:
            raise web.HTTPInternalServerError

        if not await self.bot.is_admin(user):
            raise web.HTTPForbidden

        return user, guild


class Guild(GuildBase):
    async def get(self):
        user, guild = await self.check_perms()
        guild_conf = await self.bot.db.guilds.find_one(
            {"id": guild.id}, {"_id": False, "last_message_at": False, "left": False},
        )
        if not guild_conf:
            raise web.HTTPNotFound
        guild_conf.update(
            {
                "channel_count": len(guild.channels),
                "member_count": guild.member_count,
                "role_count": len(guild.roles),
                "avatar": str(guild.icon_url),
            }
        )

        return web.json_response(text=json.dumps(guild_conf, default=date_converter))


class GuildStats(GuildBase):
    async def get(self):
        user, guild = await self.check_perms()
        cursor = self.bot.db.daily_stats.find(
            {"guild_id": guild.id},
            {"_id": False, "guild_id": False},
            sort=[("date", -1)],
        )
        limit = self.request.query.get("limit")
        stats = await cursor.to_list(int(limit) if limit else None)
        if not stats:
            raise web.HTTPNotFound

        return web.json_response(
            text=json.dumps({"id": guild.id, "stats": stats}, default=date_converter)
        )


class GuildEmojis(GuildBase):
    async def get(self):
        user, guild = await self.check_perms()
        emojis = filter(lambda e: e.guild_id == guild.id, self.bot.emojis)
        cursor = self.bot.db.emoji_stats.find(
            {"id": {"$in": [e.id for e in emojis]}},
            {"_id": False, "total": True, "id": True},
            sort=[("total", -1)],
        )
        emojis_stats = await cursor.to_list(None)
        for e in emojis_stats:
            e.update({"name": self.bot.get_emoji(e["id"]).name})
        if not emojis:
            raise web.HTTPNotFound

        return web.json_response({"id": guild.id, "emojis": emojis_stats})


class GuildMembers(GuildBase):
    async def get(self):
        user, guild = await self.check_perms()
        limit = min(int(self.request.query.get("limit", "0")), 100)
        cursor = self.bot.db.user_stats.find(
            {"guild_id": guild.id},
            {
                "_id": False,
                "guild_id": False,
                "created_at": False,
                "last_exp_at": False,
                "auto_lvl_msg": False,
            },
            sort=[("exp", -1)],
            limit=limit,
        )
        member_stats = await cursor.to_list(None)
        for member_s in member_stats:
            member = await self.bot.db.users.find_one(
                {"id": member_s["user_id"]}, {"_id": False, "name": True}
            )
            if not member:
                try:
                    member = guild.get_member(
                        member_s["user_id"]
                    ) or await guild.fetch_member(member_s["user_id"])
                except discord.HTTPException:
                    member_stats.remove(member_s)
                    continue
                else:
                    member_name = str(member)
            else:
                member_name = member["name"]

            member_s["name"] = member_name
        return web.json_response(
            text=json.dumps(
                {"id": guild.id, "members": member_stats}, ensure_ascii=False
            )
        )


class GuildChannels(GuildBase):
    @staticmethod
    def to_dict(channel: Union[discord.TextChannel, discord.VoiceChannel],):

        ch = {
            "id": channel.id,
            "name": channel.name,
            "type": str(channel.type),
            "bot_permissions": dict(channel.permissions_for(channel.guild.me)),
        }
        return ch

    async def get(self):
        user, guild = await self.check_perms()
        result = []
        for category, channels in guild.by_category():
            if category:
                category = {"id": category.id, "name": category.name}
            else:
                category = {"id": None, "name": None}
            category["channels"] = list(map(self.to_dict, channels))
            result.append(category)
        return web.json_response(
            text=json.dumps({"id": guild.id, "channels": result}, ensure_ascii=False)
        )
