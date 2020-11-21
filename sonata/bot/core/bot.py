import collections
import concurrent.futures
import hashlib
import hmac
import inspect
import traceback
from contextlib import suppress
from datetime import datetime
from json import JSONDecodeError
from typing import Union, Optional, TYPE_CHECKING, List

import aiohttp
import dbl
import discord
import twitch
from aiocache import cached, Cache
from aiocache.serializers import PickleSerializer
from aiohttp import web
from discord.ext import commands
from sentry_sdk import capture_exception, configure_scope

from sonata.bot.utils import i18n
from .cog import Cog
from .context import Context
from .errors import NoPremium

if TYPE_CHECKING:
    from logging import Logger
    from aiohttp.web_app import Application
    from aiohttp.web_request import Request


class Sonata(commands.Bot):
    def __init__(
        self,
        app: "Application",
        twitch_bearer_token: str,
        logger: "Logger" = None,
        *args,
        **kwargs,
    ):
        self.app = app
        self.config = config = app["config"]
        super().__init__(
            owner_id=self.config["bot"].owner_id,
            command_prefix=determine_prefix,
            status=discord.Status.idle,
            *args,
            **kwargs,
        )
        self.db = app["db"]
        self.logger = logger
        self.description = config["bot"].description
        self.default_prefix = config["bot"].default_prefix
        self.session = aiohttp.ClientSession()
        self.pool = concurrent.futures.ThreadPoolExecutor()
        self.launch_time = None
        self.twitch_client = twitch.Client(
            config["twitch"].client_id, twitch_bearer_token, self.session
        )
        self.dbl_client = (
            dbl.DBLClient(
                self, config["bot"].dbl_token, session=self.session, autopost=True
            )
            if config["bot"].dbl_token
            else None
        )
        self.service_guild: Optional[discord.Guild] = None
        self.errors_channel: Optional[discord.TextChannel] = None
        self.reports_channel: Optional[discord.TextChannel] = None
        self.log_channel: Optional[discord.TextChannel] = None
        cors = self.app["cors"]
        resource = cors.add(self.app.router.add_resource(r"/wh/twitch/{topic}/{id}"))
        cors.add(resource.add_route("GET", self.handler_get))
        cors.add(resource.add_route("POST", self.handler_post))
        self.cache = Cache()

    # Properties

    @property
    def uptime(self):
        return datetime.utcnow() - self.launch_time

    @property
    def description(self):
        """Applies locale when getting"""
        cogs = collections.OrderedDict(sorted(self.cogs.items()))
        desc = f"{_(self._description)}\n\n" + "\n".join(
            f"`{name}` {_(cog.description)}"
            for name, cog in cogs.items()
            if cog.description is not None
        )

        return inspect.cleandoc(desc)

    @description.setter
    def description(self, value):
        self._description = value

    @property
    def locale(self):
        return i18n.current_locale.get()

    @locale.setter
    def locale(self, value):
        i18n.current_locale.set(value)

    @property
    def invite(self):
        return discord.utils.oauth_url(
            self.user.id, permissions=discord.Permissions(1409805510),
        )

    # Handlers

    async def handler_get(self, request: "Request"):
        query = request.query
        try:
            if query["hub.mode"] == "denied":
                return web.Response(text="OK", status=200)

            if query["hub.challenge"]:
                self.dispatch(
                    "subscription_verify", query["hub.topic"], query["hub.mode"]
                )
                return web.Response(
                    body=query["hub.challenge"], content_type="text/plain"
                )
        except KeyError:
            return web.Response(text="Bad Request", status=400)

        return web.Response(text="OK", status=200)

    async def handler_post(self, request: "Request"):
        if not self.app["debug"]:
            body = await request.read()
            signature = (
                "sha256="
                + hmac.new(
                    self.config["twitch"].hub_secret.encode("utf-8"),
                    body,
                    hashlib.sha256,
                ).hexdigest()
            )
            if signature != request.headers.get("X-Hub-Signature"):
                return web.Response(text="Forbidden", status=403)

        try:
            json = await request.json()
            data = json["data"]
        except JSONDecodeError:
            return web.Response(text="Bad Request", status=400)

        try:
            data = data[0]
        except IndexError:
            data = None

        events = {"streams": "stream_changed"}
        self.dispatch(
            events[request.match_info["topic"]], data, request.match_info["id"]
        )

        return web.Response(text="OK", status=200)

    # Events

    async def on_ready(self):
        with suppress(discord.HTTPException):
            self.service_guild = service_guild = self.get_guild(
                313726240710197250
            ) or await self.fetch_guild(313726240710197250)
            self.errors_channel = service_guild.get_channel(707180649454370827)
            self.reports_channel = service_guild.get_channel(707206460878356551)
            self.log_channel = service_guild.get_channel(714881722163920917)

        await self.change_presence(
            status=discord.Status.dnd, activity=discord.Game("https://www.sonata.fun/")
        )
        if not self.launch_time:
            self.launch_time = datetime.utcnow()

        self.logger.info("Sonata is ready")

    async def on_message(self, message: discord.Message):
        if not await self.should_reply(message):
            return

        await self.process_commands(message)

    async def on_guild_join(self, guild: discord.Guild):
        await self.log_channel.send(
            f"New guild joined: {guild.name}.\n'"
            f"ID: {guild.id}.\n"
            f"Owner: {guild.owner}\n"
            f"Members: {guild.member_count}"
        )
        await self.log_channel.send(
            f"Channels: ```{', '.join(map(str, guild.channels))}```"
        )

    async def on_guild_remove(self, guild: discord.Guild):
        await self.log_channel.send(
            f"Guild removed: {guild.name}.\n'"
            f"ID: {guild.id}.\n"
            f"Owner: {guild.owner}\n"
            f"Members: {guild.member_count}"
        )

    async def on_command_error(
        self, ctx: Context, exc
    ):  # TODO: Add check error handler
        if hasattr(exc, "original"):
            exc = exc.original
        if isinstance(exc, commands.CommandNotFound):
            return
        elif isinstance(exc, commands.MissingPermissions):
            response = _(
                "You do not have enough permissions to do it."
            ) + "```diff\n- {}```".format("\n- ".join(exc.missing_perms))
        elif isinstance(exc, commands.BotMissingPermissions):
            response = _(
                "I do not have enough permissions to do it."
            ) + "```diff\n- {}```".format("\n- ".join(exc.missing_perms))
        elif isinstance(exc, discord.errors.Forbidden):
            response = _("I am missing permissions.")
        elif isinstance(exc, (commands.BadArgument, commands.BadUnionArgument)):
            response = _("Arguments specified incorrectly:```diff\n- {0}```").format(
                "\n- ".join(list(exc.args))
            )
        elif isinstance(exc, commands.MissingRequiredArgument):
            response = _("Required argument `{0}` not specified.").format(
                exc.param.name
            )
        elif isinstance(exc, discord.HTTPException):
            response = _("An error occurred while making an HTTP request.")
        elif isinstance(exc, NoPremium):
            response = _("This command is only for premium guilds.")
        elif isinstance(exc, commands.DisabledCommand):
            response = _("Command `{0}` is disabled.").format(
                ctx.command.qualified_name
            )
        elif isinstance(exc, commands.CommandOnCooldown):
            response = _("Command `{cmd}` on cooldown. Try again in **{cd}s**.").format(
                cmd=ctx.command.qualified_name, cd=round(exc.retry_after, 2)
            )
        elif isinstance(exc, commands.PrivateMessageOnly):
            response = _("This command can only be used in private messages.")
        else:
            response = None
        if not response:
            if ctx.cog and (
                getattr(Cog, "_get_overridden_method")(ctx.cog.cog_command_error)
                is not None
                or hasattr(ctx.command, "on_error")
            ):
                return
            self.logger.warning(f"Ignoring exception in command {ctx.command}: {exc}")
            self.logger.warning(
                "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            )
            with configure_scope() as scope:
                scope.set_context(
                    "context",
                    {
                        "guild": repr(ctx.guild),
                        "channel": repr(ctx.channel),
                        "author": repr(ctx.author),
                        "message": repr(ctx.message.content),
                    },
                )
                capture_exception(exc)
        else:
            try:
                await ctx.inform(response)
            except discord.Forbidden:
                await ctx.author.send(
                    _("I can't send messages to `{0}` channel.").format(
                        ctx.channel.name
                    )
                )

    # Methods

    @cached(
        ttl=60 * 5,
        serializer=PickleSerializer(),
        key_builder=lambda f, bot, ch: f"locale_{ch.id}",
    )
    async def define_locale(
        self, messageable: Union[discord.TextChannel, discord.User]
    ):
        if isinstance(messageable, discord.TextChannel):
            guild = await self.db.guilds.find_one(
                {"id": messageable.guild.id},
                {
                    "locale": True,
                    "premium": True,
                    "channels": {"$elemMatch": {"id": messageable.id}},
                },
            )
            if guild["premium"] and "channels" in guild:
                return guild["channels"][0]["locale"]

            return guild["locale"]
        else:
            user = await self.db.users.find_one(
                {"id": messageable.id}, {"locale": True}
            )
            return user["locale"]

    async def ya_define_locale(self, text: str, hint: List[str] = None):
        """Yandex Translate API"""
        params = {"key": self.config["yandex"].translate, "text": text}
        if hint:
            params["hint"] = ",".join(hint)
        async with self.session.post(
            url="https://translate.yandex.net/api/v1.5/tr.json/detect", params=params
        ) as r:
            if r.status == 200:
                data = await r.json()
                lang = data["lang"]
                self.logger.info(f"Language is defined: {lang}. Source: '{text}'")
                return lang

            return None

    def emoji(self, search_term: Union[int, str]) -> Optional[discord.Emoji]:
        """Get an emoji by ID or filename.

        Parameters
        -----------
        search_term: :class:`id` or :class:`str`
            The emoji ID or filename

        Returns
        --------
        :class:`discord.Emoji` or :obj:`None`
            Returns the `Emoji` or `None` if not found.
        """
        if isinstance(search_term, int):
            return self.get_emoji(search_term)
        if isinstance(search_term, str):
            return discord.utils.get(self.emojis, name=search_term)

    async def is_admin(self, member: discord.Member):
        if member.guild_permissions.administrator or await self.is_owner(member):
            return True
        guild = await self.db.guilds.find_one(
            {"id": member.guild.id}, {"admin_roles": True}
        )
        if (
            guild
            and "admin_roles" in guild
            and discord.utils.find(
                lambda role: role.id in guild["admin_roles"], member.roles
            )
            is not None
        ):
            return True
        return False

    async def process_commands(self, message: discord.Message):
        await self.set_locale(message)
        ctx = await self.get_context(message, cls=Context)
        # Check command is disabled
        delete_message = False
        if ctx.command:
            if ctx.guild:
                guild = await self.db.guilds.find_one(
                    {"id": message.guild.id},
                    {
                        "_id": False,
                        "disabled_cogs": True,
                        "disabled_commands": True,
                        "delete_commands": True,
                    },
                )
                if (
                    (
                        ctx.command.cog
                        and ctx.command.cog.qualified_name in guild["disabled_cogs"]
                    )
                    or ctx.command.qualified_name in guild["disabled_commands"]
                    or discord.utils.find(
                        lambda parent: parent.qualified_name
                        in guild["disabled_commands"],
                        ctx.command.parents,
                    )
                ):
                    ctx.command.enabled = False
                else:
                    ctx.command.enabled = True
                    delete_message = guild["delete_commands"]
            else:
                ctx.command.enabled = True

        await self.invoke(ctx)
        if (
            ctx.guild
            and delete_message
            and message.guild.me.guild_permissions.manage_messages
        ):
            await message.delete(delay=1.0)

    async def set_locale(self, msg: discord.Message):
        channel = msg.channel
        self.locale = await self.define_locale(
            channel if isinstance(channel, discord.TextChannel) else channel.recipient
        )

    async def guild_blacklist_check(self, message: discord.Message):
        """Return True if channel blacklisted or blacklist is disabled"""
        cursor = self.db.guilds.find(
            {"id": message.guild.id, "blacklist.channels": message.channel.id},
            {"_id": False, "blacklist.enabled": True},
        )
        if not await cursor.fetch_next:
            return False

        bl = cursor.next_object().get("blacklist")
        if bl:
            return bl.get("enabled")
        return False

    async def guild_whitelist_check(self, message: discord.Message):
        """Return True if channel whitelisted or whitelist is disabled"""
        cursor = self.db.guilds.find(
            {
                "id": message.guild.id,
                "whitelist.channels": {"$ne": message.channel.id},
            },
            {"_id": False, "whitelist.enabled": True},
        )
        if await cursor.fetch_next:
            wl = cursor.next_object().get("whitelist")
            if wl:
                return not wl.get("enabled")

        return True

    @cached(
        ttl=2,
        serializer=PickleSerializer(),
        key_builder=lambda f, b, m: f"{f.__name__}_{m.id}",
    )
    async def should_reply(self, message: discord.Message):
        """Returns whether the bot should reply to a given message"""
        if message.author.bot or not self.is_ready():
            return False

        ids = list({message.author.id, message.channel.id})
        if message.guild:
            ids.append(message.guild.id)
        cursor = self.db.blacklist.find({"id": {"$in": ids}})
        if await cursor.fetch_next:
            return False
        if message.guild:
            if (
                not message.author.guild_permissions.manage_messages
                or not await self.is_owner(message.author)
            ):
                blacklisted = await self.guild_blacklist_check(message)
                whitelisted = await self.guild_whitelist_check(message)
                if blacklisted or not whitelisted:
                    return False
        return True

    async def start(self, *args, **kwargs):
        await super().start(self.config["bot"].discord_token, *args, **kwargs)


async def determine_prefix(bot: Sonata, msg: discord.Message):
    if msg.guild:
        guild = await bot.db.guilds.find_one(
            {"id": msg.guild.id},
            {
                "custom_prefix": True,
                "premium": True,
                "channels": {"$elemMatch": {"id": msg.channel.id}},
            },
        )
        if guild["premium"] and "channels" in guild:
            prefix = guild["channels"][0]["custom_prefix"] or guild["custom_prefix"]
        else:
            prefix = guild["custom_prefix"]
    else:
        user = await bot.db.users.find_one(
            {"id": msg.author.id}, {"custom_prefix": True}
        )
        prefix = user["custom_prefix"]
    return prefix or bot.default_prefix
