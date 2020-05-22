import collections
import concurrent.futures
import hashlib
import hmac
import inspect
import traceback
from datetime import datetime
from json import JSONDecodeError
from logging import Logger
from typing import Union, Optional

import aiohttp
import dbl
import discord
import twitch
from aiohttp import web, FormData
from aiohttp.web_app import Application
from aiohttp.web_request import Request
from discord.ext import commands

from sonata.bot.utils import i18n
from .cog import Cog
from .context import Context
from .errors import NoPremium


class Sonata(commands.Bot):
    def __init__(
        self, app: Application, logger: Logger = None, *args, **kwargs,
    ):
        self.app = app
        self.db = app.get("db")
        self.logger = logger
        self.config = config = app["config"]
        super().__init__(
            owner_id=self.config["bot"].owner_id,
            command_prefix=determine_prefix,
            status=discord.Status.idle,
            *args,
            **kwargs,
        )
        self.description = self.config["bot"].description
        self.default_prefix = self.config["bot"].default_prefix
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.pool = concurrent.futures.ThreadPoolExecutor()
        self.launch_time = None
        self.twitch_client = twitch.Client(
            config.client_id, config.bearer_token, self.loop
        )
        self.dbl_client = (
            dbl.DBLClient(
                self, self.config["bot"].dbl_token, session=self.session, autopost=True
            )
            if self.config["bot"].dbl_token
            else None
        )
        self.service_guild: Optional[discord.Guild] = None
        self.errors_channel: Optional[discord.TextChannel] = None
        self.reports_channel: Optional[discord.TextChannel] = None
        self.init_handlers()

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

    # Handlers

    async def handler_get(self, request: Request):
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

    async def handler_post(self, request: Request):
        body = await request.read()
        signature = (
            "sha256="
            + hmac.new(
                self.config["twitch"].hub_secret.encode("utf-8"), body, hashlib.sha256,
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
        self.service_guild = self.get_guild(
            313726240710197250
        ) or await self.fetch_guild(313726240710197250)
        self.errors_channel = self.service_guild.get_channel(707180649454370827)
        self.reports_channel = self.service_guild.get_channel(707206460878356551)

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
        owner = self.get_user(self.owner_id) or await self.fetch_user(self.owner_id)
        await owner.send(
            f"New guild joined: {guild.name}. ID: {guild.id}. Members: {guild.member_count}"
        )
        await owner.send(f"Channels: ```{', '.join(map(str, guild.channels))}```")

    async def on_command_error(self, ctx: Context, exc):
        if hasattr(exc, "original"):
            exc = exc.original
        if isinstance(exc, commands.MissingPermissions):
            response = _("You do not have enough permissions to do it.").format(
                ctx.author.mention
            )
        elif isinstance(exc, commands.BotMissingPermissions):
            response = _("I do not have enough permissions to do it.")
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
        else:
            try:
                await ctx.inform(response)
            except discord.Forbidden:
                await ctx.author.send(
                    _("I can't send messages to `{0}` channel.").format(
                        ctx.channel.name
                    )
                )

    async def on_guild_post(self):
        data = FormData({"servers": len(self.guilds)})
        await self.session.post(
            f"https://api.server-discord.com/v2/bots/{self.user.id}/stats",
            headers={"Authorization": "SDC " + self.config["bot"].sdc_token},
            data=data,
        )
        self.logger.info("Server count posted successfully")

    # Methods

    def init_handlers(self):
        cors = self.app["cors"]
        resource = cors.add(self.app.router.add_resource(r"/wh/twitch/{topic}/{id}"))
        cors.add(resource.add_route("GET", self.handler_get))
        cors.add(resource.add_route("POST", self.handler_post))

    async def define_locale(
        self, obj: Union[discord.Message, Context, discord.TextChannel]
    ):
        if obj.guild:
            channel = obj.channel if hasattr(obj, "channel") else obj
            guild = await self.db.guilds.find_one(
                {"id": obj.guild.id},
                {
                    "locale": True,
                    "premium": True,
                    "channels": {"$elemMatch": {"id": channel.id}},
                },
            )
            if guild["premium"] and "channels" in guild:
                return guild["channels"][0]["locale"]

            return guild["locale"]
        else:
            user = await self.db.users.find_one({"id": obj.author.id}, {"locale": True})
            return user["locale"]

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

    async def process_commands(self, message: discord.Message):
        await self.set_locale(message)
        ctx = await self.get_context(message, cls=Context)
        # Check command is disabled
        if ctx.guild and ctx.command is not None:
            guild = await self.db.guilds.find_one(
                {"id": message.guild.id},
                {"_id": False, "disabled_cogs": True, "disabled_commands": True},
            )
            if (
                (
                    ctx.command.cog
                    and ctx.command.cog.qualified_name in guild["disabled_cogs"]
                )
                or ctx.command.qualified_name in guild["disabled_commands"]
                or discord.utils.find(
                    lambda parent: parent.qualified_name in guild["disabled_commands"],
                    ctx.command.parents,
                )
            ):
                ctx.command.enabled = False
            else:
                ctx.command.enabled = True

        await self.invoke(ctx)

    async def set_locale(self, msg: discord.Message):
        self.locale = await self.define_locale(msg)

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

    async def should_reply(self, message):
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
