import asyncio
import json
import re
from datetime import timedelta, datetime

import discord
from aiohttp import web
from aiohttp.web_request import Request
from discord.ext import commands
from pymongo import ReturnDocument

from sonata.bot import core
from sonata.bot.core import errors
from sonata.db.models import TwitchSubscription, TwitchSubscriptionAlertConfig

HELIX_API = "https://api.twitch.tv/helix"
STREAMS_URL = HELIX_API + "/streams"
USERS_URL = HELIX_API + "/users"
WEBHOOKS_HUB_URL = HELIX_API + "/webhooks/hub"


CALLBACK_URL = "https://sonata.fun/api/wh/twitch"


class TwitchUser(commands.Converter):
    async def convert(self, ctx: core.Context, argument):
        try:
            params = {"id": int(argument)}
        except ValueError:
            params = {"login": argument}

        async with ctx.session.get(
            USERS_URL,
            headers={
                "Client-ID": ctx.bot.config["twitch"].client_id,
                "Authorization": "Bearer " + ctx.bot.config["twitch"].bearer_token,
            },
            params=params,
        ) as resp:
            j = await resp.json()
            try:
                data = j["data"]
            except KeyError:
                raise commands.BadArgument(_("Twitch user is not found"))
        return data[0]


class TwitchMixin(core.Cog):
    twitch_colour = discord.Colour(0x6441A4)

    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self._have_data = asyncio.Event()
        self._next_sub = None
        self._task = sonata.loop.create_task(self.dispatch_subs())

    # Events

    @core.Cog.listener()
    async def on_subscription_verify(self, topic: str, mode: str):
        if mode == "subscribe":
            await self.sonata.db.twitch_subs.update_one(
                {"topic": topic}, {"$set": {"verified": True}}
            )
        elif mode == "unsubscribe":
            await self.sonata.db.twitch_subs.delete_one({"topic": topic})

    @core.Cog.listener()
    async def on_stream_changed(self, data: dict, user_id: str):
        sub = await self.sonata.db.twitch_subs.find_one(
            {"topic": STREAMS_URL + f"?user_id={user_id}"}, {"guilds": True}
        )
        try:
            guilds = sub["guilds"]
        except (KeyError, TypeError):
            return
        for alert_guild_conf in guilds:
            try:
                guild = self.sonata.get_guild(
                    alert_guild_conf["id"]
                ) or await self.sonata.fetch_guild(alert_guild_conf["id"])
            except discord.HTTPException:
                continue

            guild_conf = await self.sonata.db.guilds.find_one(
                {"id": guild.id}, {"alerts": True}
            )
            try:
                channel = guild.get_channel(
                    alert_guild_conf.get("channel")
                ) or guild.get_channel(guild_conf.get("alerts").get("channel"))
                if channel is None:
                    continue
            except AttributeError:
                continue

            if not channel.permissions_for(guild.me).send_messages:
                continue

            msg = alert_guild_conf.get("message") or guild_conf.get("message")
            if msg is None:
                msg = "{{link}}"
            replacements = [
                (r"{{\s*link\s*}}", f"https://www.twitch.tv/{data['user_name']}"),
                (r"{{\s*name\s*}}", data["user_name"]),
            ]
            for old, new in replacements:
                msg = re.sub(old, new, msg)

            if alert_guild_conf.get("embed") or guild_conf.get("embed"):
                embed = discord.Embed(
                    colour=self.twitch_colour, description=msg, title=data["user_name"]
                )
                embed.set_image(
                    url=data["thumbnail_url"].format(width=1920, height=1080)
                )
                content = ""
            else:
                content = msg
                embed = None
            mention = alert_guild_conf.get("mention") or guild_conf.get("mention")
            if mention:
                content += f"\n@{mention}"

            await channel.send(content=content, embed=embed)

    # Methods

    async def extend_subscription(
        self, sub: TwitchSubscription, lease_seconds: int = 86400
    ):
        if await self.subscribe(sub.topic, sub.callback, lease_seconds):
            expires_at = datetime.utcnow() + timedelta(seconds=lease_seconds)
            await self.sonata.db.twitch_subs.update_one(
                {"topic": sub.topic},
                {"$set": {"expires_at": expires_at, "verified": True}},
            )
            return True

        await self.sonata.db.twitch_subs.update_one(
            {"topic": sub.topic}, {"$set": {"verified": False}},
        )
        return False

    async def get_active_sub(self, *, days=10):
        cursor = self.sonata.db.twitch_subs.find(
            {
                "verified": True,
                "expires_at": {"$lte": datetime.utcnow() + timedelta(days=days)},
            },
            sort=[("expires_at", 1)],
        )
        if await cursor.fetch_next:
            sub = cursor.next_object()
            return TwitchSubscription(**sub)
        else:
            return None

    async def wait_for_active_subs(self, *, days=10):
        sub = await self.get_active_sub(days=days)
        if sub is not None:
            self._have_data.set()
            return sub

        self._have_data.clear()
        self._next_sub = None
        await self._have_data.wait()
        return await self.get_active_sub(days=days)

    async def dispatch_subs(self):
        try:
            while not self.sonata.is_closed():
                sub = self._next_sub = await self.wait_for_active_subs(days=40)
                now = datetime.utcnow()
                if sub.expires_at >= now:
                    to_sleep = (sub.expires_at - now).total_seconds()
                    await asyncio.sleep(to_sleep)

                await self.extend_subscription(sub)
        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed):
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_subs())

    async def is_subscription_exist(self, topic: str):
        cursor = self.sonata.db.twitch_subs.find({"topic": topic}, {"id": True})
        return await cursor.fetch_next

    async def is_subscription_verified(self, topic: str):
        cursor = self.sonata.db.twitch_subs.find({"topic": topic}, {"verified": True})
        if await cursor.fetch_next:
            return cursor.next_object()["verified"]

        raise errors.SubscriptionNotFound

    @staticmethod
    def make_params(topic: str, callback: str, mode: str, lease_seconds: int = 86400):
        return {
            "hub.callback": callback,
            "hub.mode": mode,
            "hub.topic": topic,
            "hub.lease_seconds": lease_seconds,
        }

    async def subscribe(self, topic: str, callback: str, lease_seconds: int = 86400):
        """Return True if successful subscription"""
        params = self.make_params(topic, callback, "subscribe", lease_seconds)
        async with self.sonata.session.post(
            WEBHOOKS_HUB_URL,
            headers={
                "Client-ID": self.sonata.config["twitch"].client_id,
                "Authorization": "Bearer " + self.sonata.config["twitch"].bearer_token,
            },
            params=params,
        ) as resp:
            if resp.status != 202:
                return False
        return True

    # Commands

    @core.group(invoke_without_command=True)
    @commands.is_owner()
    async def twitch(self, ctx: core.Context):
        if ctx.invoked_subcommand is not None:
            return await ctx.send_help()
        cursor = ctx.db.twitch_subs.find(
            {"guilds.id": ctx.guild.id, "verified": True}, {"login": True}
        )
        users = []
        while await cursor.fetch_next:
            users.append(cursor.next_object()["login"])
        await ctx.inform(", ".join(users), title=_("Tracked users"))

    @twitch.command(name="add")
    async def twitch_add(self, ctx: core.Context, user: TwitchUser()):
        topic = STREAMS_URL + f"?user_id={user['id']}"
        callback = CALLBACK_URL + f"/streams/{user['id']}"
        config = TwitchSubscriptionAlertConfig(id=ctx.guild.id)
        if await self.is_subscription_exist(topic):
            sub = TwitchSubscription(
                **(
                    await ctx.db.twitch_subs.find_one_and_update(
                        {"topic": topic},
                        {"$addToSet": {"guilds": config.dict()}},
                        return_document=ReturnDocument.AFTER,
                    )
                )
            )
        else:
            now = ctx.message.created_at
            sub = TwitchSubscription(
                created_at=now,
                guilds=[config],
                id=user["id"],
                login=user["login"],
                topic=topic,
                callback=callback,
            )
            await ctx.db.twitch_subs.insert_one(sub.dict())
        if not await self.is_subscription_verified(topic):
            async with ctx.typing():
                if not await self.extend_subscription(sub):
                    return await ctx.inform(_("An error occurred while subscribing."))

                expires_at = datetime.utcnow() + timedelta(seconds=864000)
                await ctx.db.twitch_subs.update_one(
                    {"topic": topic}, {"$set": {"expires_at": expires_at}},
                )
                self._have_data.set()
        await ctx.inform(
            _("User {0} is now tracked in this guild.").format(user["login"])
        )

    @twitch.command(name="clear")
    async def twitch_clear(self, ctx: core.Context):
        await ctx.db.twitch_subs.update_many(
            {"guilds.id": ctx.guild.id}, {"$pull": {"guilds": {"id": ctx.guild.id}}}
        )
        await ctx.inform(_("The list of tracked users in this guild has been cleared."))

    @twitch.command(name="remove")
    async def twitch_remove(self, ctx: core.Context, user: TwitchUser()):
        topic = STREAMS_URL + f"?user_id={user['id']}"
        if await self.is_subscription_exist(topic):
            result = await ctx.db.twitch_subs.update_one(
                {"topic": topic, "guilds.id": ctx.guild.id},
                {"$pull": {"guilds": {"id": ctx.guild.id}}},
            )
            if result.modified_count != 0:
                return await ctx.inform(
                    _("User {0} is no longer being tracked in this guild.").format(
                        user["login"]
                    )
                )
        await ctx.inform(
            _("User {0} is not tracked in this guild.").format(user["login"])
        )
