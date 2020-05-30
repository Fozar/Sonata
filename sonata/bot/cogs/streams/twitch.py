import asyncio
import re
import weakref
from contextlib import suppress
from datetime import timedelta, datetime
from typing import Optional

import discord
import twitch
from discord.ext import commands
from twitch.webhook import StreamChanged

from sonata.bot import core
from sonata.bot.core import errors
from sonata.db.models import SubscriptionAlertConfig, TwitchSubscriptionStatus

HELIX_API = "https://api.twitch.tv/helix"
STREAMS_URL = HELIX_API + "/streams"


CALLBACK_URL = "https://sonata.fun/api/wh/twitch"


def limit_subs():
    async def pred(ctx: core.Context):
        subs = await ctx.db.twitch_subs.count_documents({"guilds.id": ctx.guild.id})
        if subs >= 5:
            return await core.is_premium(ctx)

        return True

    return commands.check(pred)


class TwitchUserConverter(commands.Converter):
    async def convert(self, ctx: core.Context, argument):
        client = ctx.bot.twitch_client
        try:
            user = await client.get_user(str(int(argument)))
        except ValueError:
            user = await client.get_user(login=argument)
        if user is None:
            raise commands.BadArgument(_("Twitch user is not found"))
        return user


class TwitchSubscriptionConverter(commands.Converter):
    def __init__(self):
        self.user = None
        self.topic = None

    async def convert(self, ctx: core.Context, argument):
        self.user = user = await TwitchUserConverter().convert(ctx, argument)
        self.topic = topic = StreamChanged(user.id)
        cursor = ctx.bot.db.twitch_subs.find({"topic": str(topic)}, {"id": True})
        if not await cursor.fetch_next:
            raise commands.BadArgument(
                _("User {0} is not tracked in this guild.").format(user.display_name)
            )
        return self


class TwitchMixin(core.Cog):
    twitch_colour = discord.Colour(0x6441A4)

    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self.twitch = sonata.twitch_client
        self._locks = weakref.WeakValueDictionary()
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
    async def on_stream_changed(self, data: Optional[dict], user_id: str):
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        async with lock:
            if not data:  # Maybe it's just a reconnect
                await asyncio.sleep(60)  # Check to avoid spam alerts.
                stream = await self.twitch.get_stream(user_id)
            else:
                stream = twitch.Stream(self.twitch, data)
            if stream:
                await stream.get_game()
                user = await stream.get_user()
            else:
                user = await self.twitch.get_user(user_id)
            topic = StreamChanged(user_id)
            sub_status = await self.sonata.db.twitch_subs.find_one(
                {"topic": str(topic)}, {"guilds": True}
            )
            try:
                alert_configs = sub_status["guilds"]
            except (KeyError, TypeError):
                return  # No subs

            for alert_config in alert_configs:
                await self.process_alert(alert_config, topic, stream, user)

    # Methods

    async def process_alert(
        self,
        alert_config: dict,
        topic: twitch.Topic,
        stream: twitch.Stream,
        user: twitch.User,
    ):
        try:
            guild = self.sonata.get_guild(
                alert_config["id"]
            ) or await self.sonata.fetch_guild(alert_config["id"])
        except discord.HTTPException:
            return

        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": guild.id}, {"alerts": True}
        )
        default_config = guild_conf["alerts"]

        with suppress(KeyError, AttributeError, discord.HTTPException):
            channel_id, message_id = alert_config["message_id"].split("-")
            try:
                channel = guild.get_channel(int(channel_id))
                message = await channel.fetch_message(int(message_id))
            except (discord.HTTPException, AttributeError):
                raise
            else:
                if not stream:
                    await self.close_alert(message, default_config, alert_config, user)
                else:
                    await self.update_alert(
                        message, alert_config, default_config, stream
                    )
            finally:
                await self.sonata.db.twitch_subs.update_one(
                    {"topic": str(topic), "guilds.id": guild.id},
                    {"$set": {"guilds.$.message_id": None}},
                )
            return

        if not stream:
            return

        try:
            msg = await self.new_alert(guild, default_config, alert_config, stream)
        except discord.HTTPException:
            return

        if msg:
            await self.sonata.db.twitch_subs.update_one(
                {"topic": str(topic), "guilds.id": guild.id},
                {"$set": {"guilds.$.message_id": f"{msg.channel.id}-{msg.id}"}},
            )

    async def close_alert(
        self,
        message: discord.Message,
        default_config: dict,
        alert_config: dict,
        user: twitch.User,
    ):
        embed = next(iter(message.embeds), None)
        if embed is None:
            return

        close_cnt = (
            alert_config["close_message"] or default_config["close_message"] or ""
        )
        close_cnt = self._format_content(close_cnt, user)
        await self.sonata.set_locale(message)
        embed.title = _("Stream is offline")
        embed.description = close_cnt or discord.embeds.EmptyEmbed
        embed.set_image(url=user.offline_image_url)
        embed.remove_field(1)
        await message.edit(content=None, embed=embed)

    async def new_alert(
        self,
        guild: discord.Guild,
        default_config: dict,
        alert_config: dict,
        stream: twitch.Stream,
    ):
        if not default_config["enabled"] or not alert_config["enabled"]:
            return

        channel = guild.get_channel(alert_config["channel"]) or guild.get_channel(
            default_config["channel"]
        )
        if channel is None:
            return

        cnt = alert_config["message"] or default_config["message"] or "{{link}}"
        cnt = self._format_content(cnt, stream.user, stream, stream.game)
        self.sonata.locale = await self.sonata.define_locale(channel)
        embed = self._make_alert_embed(cnt, stream, stream.user, stream.game)
        content = None
        with suppress(discord.HTTPException):
            me = guild.me or await guild.fetch_member(self.sonata.user.id)
            perms = channel.permissions_for(me)
            if not perms.send_messages:
                return

            if perms.mention_everyone:
                mention = (
                    lambda conf: conf["mention"]["value"]
                    if conf["mention"]["enabled"]
                    else None
                )
                mention = mention(
                    default_config
                    if alert_config["mention"]["inherit"]
                    else alert_config
                )
                if mention:
                    content = f"\n@{mention}"

        return await channel.send(content=content, embed=embed)

    async def update_alert(
        self,
        message: discord.Message,
        alert_config: dict,
        default_config: dict,
        stream: twitch.Stream,
    ):
        cnt = alert_config["message"] or default_config["message"] or "{{link}}"
        cnt = self._format_content(cnt, stream.user, stream, stream.game)
        await self.sonata.set_locale(message)
        embed = self._make_alert_embed(cnt, stream, stream.user, stream.game)
        await message.edit(embed=embed)

    @staticmethod
    def _format_content(
        message: str,
        user: twitch.User,
        stream: twitch.Stream = None,
        game: twitch.Game = None,
    ):
        replacements = [
            (r"{{\s*link\s*}}", f"https://www.twitch.tv/{user.login}"),
            (r"{{\s*name\s*}}", user.display_name),
            (r"{{\s*views\s*}}", str(user.view_count)),
        ]
        if stream:
            replacements.extend(
                [
                    (r"{{\s*title\s*}}", stream.title),
                    (r"{{\s*viewers\s*}}", str(stream.viewer_count)),
                ]
            )
        if game:
            replacements.append((r"{{\s*game\s*}}", game.name))
        for old, new in replacements:
            message = re.sub(old, new, message, flags=re.I)
        return message

    def _make_alert_embed(
        self,
        description: str,
        stream: twitch.Stream,
        user: twitch.User,
        game: twitch.Game,
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
        embed.add_field(name=_("Game"), value=game.name)
        embed.add_field(name=_("Viewers"), value=str(stream.viewer_count))
        embed.add_field(name=_("Views"), value=str(user.view_count))
        return embed

    async def extend_subscription(
        self, sub_status: TwitchSubscriptionStatus, lease_seconds: int = 864000
    ):
        try:
            topic = twitch.StreamChanged.from_uri(sub_status.topic)
            subscription = self.twitch.create_subscription(
                sub_status.callback,
                topic,
                lease_seconds,
                self.sonata.config["twitch"].hub_secret,
            )
            await subscription.extend()
            expires_at = datetime.utcnow() + timedelta(seconds=lease_seconds)
            await self.sonata.db.twitch_subs.update_one(
                {"topic": sub_status.topic}, {"$set": {"expires_at": expires_at}},
            )
            return True
        except twitch.HTTPException:
            await self.sonata.db.twitch_subs.update_one(
                {"topic": sub_status.topic}, {"$set": {"verified": False}},
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
            sub_status = cursor.next_object()
            return TwitchSubscriptionStatus(**sub_status)
        else:
            return None

    async def wait_for_active_subs(self, *, days=10):
        sub_status = await self.get_active_sub(days=days)
        if sub_status is not None:
            self._have_data.set()
            return sub_status

        self._have_data.clear()
        self._next_sub = None
        await self._have_data.wait()
        return await self.get_active_sub(days=days)

    async def dispatch_subs(self):
        try:
            while not self.sonata.is_closed():
                sub_status = self._next_sub = await self.wait_for_active_subs(days=40)
                now = datetime.utcnow()
                if sub_status.expires_at >= now:
                    to_sleep = (sub_status.expires_at - now).total_seconds()
                    await asyncio.sleep(to_sleep)

                await asyncio.sleep(30)
                await self.extend_subscription(sub_status)
        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed):
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_subs())

    async def is_subscription_exist(self, topic: twitch.webhook.Topic):
        cursor = self.sonata.db.twitch_subs.find({"topic": str(topic)}, {"id": True})
        return await cursor.fetch_next

    async def is_subscription_verified(self, topic: twitch.webhook.Topic):
        cursor = self.sonata.db.twitch_subs.find(
            {"topic": str(topic)}, {"verified": True}
        )
        if await cursor.fetch_next:
            return cursor.next_object()["verified"]

        raise errors.SubscriptionNotFound

    # Commands

    @core.group(name="twitch", invoke_without_command=True)
    @commands.has_guild_permissions(manage_messages=True)
    async def _twitch(self, ctx: core.Context):
        _("""Twitch alerts""")
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
    @limit_subs()
    async def twitch_add(self, ctx: core.Context, user: TwitchUserConverter()):
        _(
            """Adds the user to the list of tracked streamers
        
        Example
        - twitch add ninja"""
        )
        topic = StreamChanged(user.id)
        callback = f"{CALLBACK_URL}/streams/{user.id}"
        subscription = self.twitch.create_subscription(
            callback, topic, 864000, ctx.bot.config["twitch"].hub_secret,
        )
        alert_config = SubscriptionAlertConfig(id=ctx.guild.id)
        if await self.is_subscription_exist(topic):
            await ctx.db.twitch_subs.update_one(
                {"topic": str(topic)}, {"$addToSet": {"guilds": alert_config.dict()}},
            )
        else:
            now = ctx.message.created_at
            sub_status = TwitchSubscriptionStatus(
                created_at=now,
                guilds=[alert_config],
                id=user.id,
                login=user.login,
                topic=str(topic),
                callback=callback,
            ).dict()
            await ctx.db.twitch_subs.insert_one(sub_status)
        if not await self.is_subscription_verified(topic):
            async with ctx.typing():
                try:
                    await subscription.subscribe()
                except twitch.HTTPException:
                    return await ctx.inform(_("An error occurred while subscribing."))

                expires_at = datetime.utcnow() + timedelta(seconds=864000)
                await ctx.db.twitch_subs.update_one(
                    {"topic": str(topic)}, {"$set": {"expires_at": expires_at}},
                )
                self._have_data.set()
        await ctx.inform(
            _("User {0} is now tracked in this guild.").format(user.display_name)
        )
        resp = await self.twitch.http.get_streams([user.id])
        data = resp["data"]
        if data:
            await self.on_stream_changed(data[0], user.id)

    @_twitch.command(name="clear")
    async def twitch_clear(self, ctx: core.Context):
        _("""Clears the list of tracked streamers""")
        await ctx.db.twitch_subs.update_many(
            {"guilds.id": ctx.guild.id}, {"$pull": {"guilds": {"id": ctx.guild.id}}}
        )
        await ctx.inform(_("The list of tracked users in this guild has been cleared."))

    @_twitch.command(name="remove")
    async def twitch_remove(self, ctx: core.Context, user: TwitchSubscriptionConverter):
        _(
            """Removes a user from the list of tracked streamers
        
        This will also reset all non-default settings related to this user.
        
        Example
        - twitch remove ninja"""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$pull": {"guilds": {"id": ctx.guild.id}}},
        )
        return await ctx.inform(
            _("User {0} is no longer being tracked in this guild.").format(
                user.user.display_name
            )
        )

    @_twitch.command(name="disable")
    @core.premium_only()
    async def twitch_disable(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _(
            """Disables alerts from the specified streamer
        
        Example
        - twitch disable ninja"""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.enabled": False}},
        )
        return await ctx.inform(
            _("Alerts from {0} are disabled.").format(user.user.display_name)
        )

    @_twitch.command(name="enable")
    @core.premium_only()
    async def twitch_enable(self, ctx: core.Context, user: TwitchSubscriptionConverter):
        _(
            """Enables alerts from the specified streamer
        
        Example
        - twitch enable ninja"""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.enabled": True}},
        )
        return await ctx.inform(
            _("Alerts from {0} are enabled.").format(user.user.display_name)
        )

    @_twitch.group(name="set")
    @core.premium_only()
    async def twitch_set(self, ctx: core.Context):
        _("""Sets alert settings for specified user""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @twitch_set.command(name="channel")
    async def twitch_set_channel(
        self,
        ctx: core.Context,
        user: TwitchSubscriptionConverter(),
        channel: discord.TextChannel,
    ):
        _(
            """Sets alert channel for specified user

        Example
        - twitch set channel ninja #TextChannel"""
        )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))

        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.channel": channel.id}},
        )
        return await ctx.inform(
            _("Alert channel set for {0}.").format(user.user.display_name)
        )

    @twitch_set.command(name="offline.message")
    async def twitch_set_offline_message(
        self,
        ctx: core.Context,
        user: TwitchSubscriptionConverter,
        *,
        message: commands.clean_content(),
    ):
        _(
            """Sets offline alert message for specified user

        Markdown is allowed.

        Replacements
        {{link}} - stream link
        {{name}} - streamer name
        {{views}} - user's views count

        Example
        - twitch set offline.message ninja {{name}} if offline."""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.close_message": message}},
        )
        return await ctx.inform(
            _("Alert offline message set for {0}.").format(user.user.display_name)
        )

    @twitch_set.command(name="message")
    async def twitch_set_message(
        self,
        ctx: core.Context,
        user: TwitchSubscriptionConverter,
        *,
        message: commands.clean_content(),
    ):
        _(
            """Sets alert message for specified user

        Markdown is allowed.

        Replacements
        {{link}} - stream link
        {{name}} - streamer name
        {{title}} - stream title
        {{game}} - game name
        {{viewers}} - viewers count
        {{views}} - user's views count

        Example
        - twitch set message ninja {{name}} began broadcasting "{{game}}". Link: {{link}}
        """
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.message": message}},
        )
        return await ctx.inform(
            _("Alert message set for {0}.").format(user.user.display_name)
        )

    @twitch_set.group(name="mention")
    async def twitch_set_mention(self, ctx: core.Context):
        _("""Toggles alert mentions for specified user""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @twitch_set_mention.command(name="everyone")
    async def twitch_set_mention_everyone(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _(
            """Sets alert mentions to `@everyone` for specified user

        The bot must have the permission to mention everyone."""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {
                "$set": {
                    "guilds.$.mention.value": "everyone",
                    "guilds.$.mention.inherit": False,
                }
            },
        )
        return await ctx.inform(
            _("Alerts will mention `@everyone` for {0}.").format(user.user.display_name)
        )

    @twitch_set_mention.command(name="here")
    async def twitch_set_mention_here(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _(
            """Sets alert mentions to `@here` for specified user

        The bot must have the permission to mention everyone."""
        )
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {
                "$set": {
                    "guilds.$.mention.value": "here",
                    "guilds.$.mention.inherit": False,
                }
            },
        )
        return await ctx.inform(
            _("Alerts will mention `here` for {0}.").format(user.user.display_name)
        )

    @twitch_set_mention.command(name="enable")
    async def twitch_set_mention_enable(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _("""Enables alert mentions for specified user""")
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {
                "$set": {
                    "guilds.$.mention.enabled": True,
                    "guilds.$.mention.inherit": False,
                }
            },
        )
        return await ctx.inform(
            _("Alert mentions enabled for {0}.").format(user.user.display_name)
        )

    @twitch_set_mention.command(name="disable")
    async def twitch_set_mention_disable(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _("""Disables alert mentions for specified user""")
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {
                "$set": {
                    "guilds.$.mention.enabled": False,
                    "guilds.$.mention.inherit": False,
                }
            },
        )
        return await ctx.inform(
            _("Alert mentions disabled for {0}.").format(user.user.display_name)
        )

    @twitch_set_mention.command(name="inherit")
    async def twitch_set_mention_inherit(
        self, ctx: core.Context, user: TwitchSubscriptionConverter
    ):
        _("""Inherits mentions settings from default settings""")
        await ctx.db.twitch_subs.update_one(
            {"topic": str(user.topic), "guilds.id": ctx.guild.id},
            {"$set": {"guilds.$.mention.inherit": True}},
        )
        return await ctx.inform(
            _("Mention settings inherited from default settings for {0}.").format(
                user.user.display_name
            )
        )
