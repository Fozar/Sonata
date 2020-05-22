import asyncio
import re
from contextlib import suppress
from datetime import timedelta, datetime

import discord
import twitch
from discord.ext import commands
from pymongo import ReturnDocument

from sonata.bot import core
from sonata.bot.core import errors
from sonata.db.models import TwitchSubscription, SubscriptionAlertConfig

HELIX_API = "https://api.twitch.tv/helix"
STREAMS_URL = HELIX_API + "/streams"


CALLBACK_URL = "https://sonata.fun/api/wh/twitch"


class TwitchUserConverter(commands.Converter):
    async def convert(self, ctx: core.Context, argument):
        streams = ctx.bot.get_cog("Streams")
        client = streams.twitch
        try:
            user = await client.get_user(int(argument))
        except ValueError:
            user = await client.get_user(user_login=argument)
        if user is None:
            raise commands.BadArgument(_("Twitch user is not found"))
        return user


class TwitchMixin(core.Cog):
    twitch_colour = discord.Colour(0x6441A4)

    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        config = sonata.config["twitch"]
        self.twitch = twitch.Client(config.client_id, config.bearer_token, sonata.loop)
        self._have_data = asyncio.Event()
        self._next_sub = None
        self._task = sonata.loop.create_task(self.dispatch_subs())

    def cog_unload(self):
        self._task.cancel()

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
        topic = STREAMS_URL + f"?user_id={user_id}"
        sub = await self.sonata.db.twitch_subs.find_one(
            {"topic": topic}, {"guilds": True}
        )
        try:
            guilds = sub["guilds"]
        except (KeyError, TypeError):
            return

        for alert_conf in guilds:
            try:
                guild = self.sonata.get_guild(
                    alert_conf["id"]
                ) or await self.sonata.fetch_guild(alert_conf["id"])
            except discord.HTTPException:
                continue

            if not data:
                continue

            stream = twitch.Stream(self.twitch, data)
            await self.new_alert(guild, alert_conf, topic, stream)

    # Methods

    @staticmethod
    def make_custom_message(
        message: str, stream: twitch.Stream, user: twitch.User, game: twitch.Game
    ):
        replacements = [
            (r"{{\s*link\s*}}", f"https://www.twitch.tv/{stream.user_name.lower()}"),
            (r"{{\s*name\s*}}", stream.user_name),
            (r"{{\s*title\s*}}", stream.title),
            (r"{{\s*game\s*}}", game.name),
            (r"{{\s*viewers\s*}}", str(stream.viewer_count)),
            (r"{{\s*views\s*}}", str(user.view_count)),
        ]
        for old, new in replacements:
            message = re.sub(old, new, message, flags=re.I)
        return message

    def make_alert_embed(
        self, description: str, stream: twitch.Stream, user: twitch.User
    ):
        embed = discord.Embed(
            colour=self.twitch_colour,
            description=description,
            title=stream.title,
            timestamp=stream.started_at,
        )
        url = f"https://www.twitch.tv/{user.login}"
        embed.set_author(
            name=user.display_name, url=url, icon_url=user.profile_image_url
        )
        embed.url = url
        embed.set_image(url=stream.thumbnail_url())
        embed.set_footer(
            text="Twitch", icon_url="https://www.sonata.fun/img/TwitchGlitchPurple.png"
        )
        return embed

    async def new_alert(
        self, guild: discord.Guild, sub_guild: dict, topic: str, stream: twitch.Stream
    ):
        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": guild.id}, {"alerts": True}
        )
        guild_alerts = guild_conf["alerts"]
        if not guild_alerts["enabled"] or not sub_guild["enabled"]:
            return

        channel = guild.get_channel(sub_guild["channel"]) or guild.get_channel(
            guild_alerts["channel"]
        )
        if channel is None:
            return

        cnt = sub_guild["message"] or guild_alerts["message"] or "{{link}}"
        cnt = self.make_custom_message(cnt, stream)

        user = await stream.get_user()
        embed = self.make_alert_embed(cnt, stream, user)
        content = None
        with suppress(discord.HTTPException):
            me = guild.me or await guild.fetch_member(self.sonata.user.id)
            if not channel.permissions_for(me).send_messages:
                return
            if channel.permissions_for(me).mention_everyone:
                mention = sub_guild["mention"] or guild_alerts["mention"]
                if mention:
                    content = f"\n@{mention}"

        with suppress(discord.HTTPException):
            msg = await channel.send(content=content, embed=embed)
            await self.sonata.db.twitch_subs.update_one(
                {"topic": topic, "guilds.id": guild.id},
                {"$set": {"guilds.$.message_id": f"{msg.channel.id}-{msg.id}"}},
            )

    async def extend_subscription(
        self, sub: TwitchSubscription, lease_seconds: int = 864000
    ):
        try:
            await self.twitch.subscribe_to_events(
                sub.callback, sub.topic, lease_seconds, sub.secret
            )
            expires_at = datetime.utcnow() + timedelta(seconds=lease_seconds)
            await self.sonata.db.twitch_subs.update_one(
                {"topic": sub.topic}, {"$set": {"expires_at": expires_at}},
            )
            return True
        except twitch.HTTPException:
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

    # Commands

    @core.group(name="twitch", invoke_without_command=True)
    @commands.is_owner()
    async def _twitch(self, ctx: core.Context):
        if ctx.invoked_subcommand is not None:
            return await ctx.send_help()
        cursor = ctx.db.twitch_subs.find(
            {"guilds.id": ctx.guild.id, "verified": True}, {"login": True}
        )
        users = []
        while await cursor.fetch_next:
            users.append(cursor.next_object()["login"])
        await ctx.inform(", ".join(users), title=_("Tracked users"))

    @_twitch.command(name="add")
    async def twitch_add(self, ctx: core.Context, user: TwitchUserConverter()):
        topic = f"{STREAMS_URL}?user_id={user.id}"
        callback = f"{CALLBACK_URL}/streams/{user.id}"
        alert_config = SubscriptionAlertConfig(id=ctx.guild.id)
        if await self.is_subscription_exist(topic):
            sub_doc = await ctx.db.twitch_subs.find_one_and_update(
                {"topic": topic},
                {"$addToSet": {"guilds": alert_config.dict()}},
                return_document=ReturnDocument.AFTER,
            )
            sub = TwitchSubscription(**sub_doc)
        else:
            now = ctx.message.created_at
            sub = TwitchSubscription(
                created_at=now,
                guilds=[alert_config],
                id=user.id,
                login=user.login,
                topic=topic,
                callback=callback,
                secret=ctx.bot.config["twitch"].hub_secret,
            )
            await ctx.db.twitch_subs.insert_one(sub.dict())
        if not await self.is_subscription_verified(topic):
            async with ctx.typing():
                if not await self.extend_subscription(sub, 864000):
                    return await ctx.inform(_("An error occurred while subscribing."))

                expires_at = datetime.utcnow() + timedelta(seconds=864000)
                await ctx.db.twitch_subs.update_one(
                    {"topic": topic}, {"$set": {"expires_at": expires_at}},
                )
                self._have_data.set()
        await ctx.inform(
            _("User {0} is now tracked in this guild.").format(user.display_name)
        )

    @_twitch.command(name="clear")
    async def twitch_clear(self, ctx: core.Context):
        await ctx.db.twitch_subs.update_many(
            {"guilds.id": ctx.guild.id}, {"$pull": {"guilds": {"id": ctx.guild.id}}}
        )
        await ctx.inform(_("The list of tracked users in this guild has been cleared."))

    @_twitch.command(name="remove")
    async def twitch_remove(self, ctx: core.Context, user: TwitchUserConverter()):
        topic = STREAMS_URL + f"?user_id={user.id}"
        if await self.is_subscription_exist(topic):
            result = await ctx.db.twitch_subs.update_one(
                {"topic": topic, "guilds.id": ctx.guild.id},
                {"$pull": {"guilds": {"id": ctx.guild.id}}},
            )
            if result.modified_count != 0:
                return await ctx.inform(
                    _("User {0} is no longer being tracked in this guild.").format(
                        user.display_name
                    )
                )
        await ctx.inform(
            _("User {0} is not tracked in this guild.").format(user.display_name)
        )
