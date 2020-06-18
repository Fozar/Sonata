import datetime as dt
import json
import time

import discord
from aiohttp import web
from aiohttp_cors import CorsViewMixin
from aiohttp_security import check_authorized


def date_converter(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return int(time.mktime(o.timetuple()))


async def check_guild(bot, guild_id) -> discord.Guild:
    try:
        return bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
    except discord.Forbidden:
        raise web.HTTPForbidden
    except discord.HTTPException:
        raise web.HTTPInternalServerError


class Guilds(web.View, CorsViewMixin):
    async def get(self):
        bot = self.request.app.get("bot")
        guilds = len(bot.guilds) if bot else 0
        members = len(bot.users) if bot else 0
        return web.json_response({"guilds": guilds, "members": members})


class Guild(web.View, CorsViewMixin):
    async def get(self):
        user_id = int(await check_authorized(self.request))
        guild_id = int(self.request.match_info["id"])
        bot = self.request.app.get("bot")
        guild = await check_guild(bot, guild_id)
        if guild.owner.id != user_id:
            raise web.HTTPForbidden
        guild_conf = await bot.db.guilds.find_one(
            {"id": guild_id}, {"_id": False, "last_message_at": False, "left": False},
        )
        if not guild_conf:
            raise web.HTTPNotFound

        return web.json_response(text=json.dumps(guild_conf, default=date_converter))


class GuildStats(web.View, CorsViewMixin):
    async def get(self):
        user_id = int(await check_authorized(self.request))
        guild_id = int(self.request.match_info["id"])
        bot = self.request.app.get("bot")
        guild = await check_guild(bot, guild_id)
        if guild.owner.id != user_id:
            raise web.HTTPForbidden

        cursor = bot.db.daily_stats.find(
            {"guild_id": guild_id},
            {"_id": False, "guild_id": False},
            sort=[("date", -1)],
        )
        limit = self.request.query.get("limit")
        stats = await cursor.to_list(int(limit) if limit else None)
        if not stats:
            raise web.HTTPNotFound

        return web.json_response(
            text=json.dumps({"id": guild_id, "stats": stats}, default=date_converter)
        )


class GuildEmojis(web.View, CorsViewMixin):
    async def get(self):
        user_id = int(await check_authorized(self.request))
        guild_id = int(self.request.match_info["id"])
        bot = self.request.app.get("bot")
        guild = await check_guild(bot, guild_id)
        if guild.owner.id != user_id:
            raise web.HTTPForbidden

        emojis = filter(lambda e: e.guild_id == guild_id, bot.emojis)
        cursor = bot.db.emoji_stats.find(
            {"id": {"$in": [e.id for e in emojis]}},
            {"_id": False, "total": True, "id": True},
            sort=[("total", -1)],
        )
        emojis_stats = await cursor.to_list(None)
        for e in emojis_stats:
            e.update({"name": bot.get_emoji(e['id']).name})
        if not emojis:
            raise web.HTTPNotFound

        return web.json_response({"id": guild_id, "emojis": emojis_stats})


class GuildMembers(web.View, CorsViewMixin):
    async def get(self):
        try:
            user_id = int(await check_authorized(self.request))
            guild_id = int(self.request.match_info["id"])
        except TypeError:
            raise web.HTTPBadRequest

        bot = self.request.app.get("bot")
        guild = await check_guild(bot, guild_id)
        if guild.owner.id != user_id:
            raise web.HTTPForbidden

        limit = min(int(self.request.query.get("limit", "0")), 100)
        cursor = bot.db.user_stats.find(
            {"guild_id": guild_id},
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
            member = await bot.db.users.find_one(
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
                {"id": guild_id, "members": member_stats}, ensure_ascii=False
            )
        )
