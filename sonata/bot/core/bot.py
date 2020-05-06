import inspect
import traceback
from datetime import datetime
from logging import Logger
from typing import Union, Optional

import aiohttp
import dbl
import discord
from aiohttp.web_app import Application
from discord.ext import commands

from sonata.bot.utils import i18n
from .cog import Cog
from .context import Context
from .errors import NoPremium
from .help import HelpCommand


class Sonata(commands.Bot):
    def __init__(
        self, app: Application, logger: Logger = None, *args, **kwargs,
    ):
        self.app = app
        self.db = app.get("db")
        self.logger = logger
        self.config = app["config"]
        super().__init__(
            owner_id=self.config["bot"].owner_id,
            command_prefix=determine_prefix,
            status=discord.Status.idle,
            help_command=HelpCommand(),
            *args,
            **kwargs,
        )
        self.description = self.config["bot"].description
        self.default_prefix = self.config["bot"].default_prefix
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.launch_time = None
        self.dblpy = (
            dbl.DBLClient(
                self, self.config["bot"].dbl_token, session=self.session, autopost=True
            )
            if self.config["bot"].dbl_token
            else None
        )
        self.service_guild: Optional[discord.Guild] = None
        self.errors_channel: Optional[discord.TextChannel] = None
        self.reports_channel: Optional[discord.TextChannel] = None

    # Properties

    @property
    def uptime(self):
        return datetime.utcnow() - self.launch_time

    @property
    def description(self):
        """Applies locale when getting"""
        return inspect.cleandoc(_(self._description))

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
            self.user.id, permissions=discord.Permissions(1141370054)
        )

    # Events

    async def on_ready(self):
        self.help_command.cog = self.get_cog("General")
        self.service_guild = self.get_guild(
            313726240710197250
        ) or await self.fetch_guild(313726240710197250)
        self.errors_channel = self.service_guild.get_channel(707180649454370827)
        self.reports_channel = self.service_guild.get_channel(707206460878356551)

        await self.change_presence(status=discord.Status.dnd)
        if not self.launch_time:
            self.launch_time = datetime.utcnow()
        self.logger.info("Sonata is ready")

    async def on_message(self, message: discord.Message):
        if not self.should_reply(message):
            return

        await self.process_commands(message)

    async def on_guild_join(self, guild: discord.Guild):
        owner = self.get_user(self.owner_id) or await self.fetch_user(self.owner_id)
        await owner.send(
            f"New guild joined: {guild.name}. ID: {guild.id}. Members: {guild.member_count}"
        )
        await owner.send(f"Channels: ```{', '.join(map(str, guild.channels))}```")

    async def on_command_error(self, ctx: Context, exception):
        response = ""
        if hasattr(exception, "original"):
            exception = exception.original
        if isinstance(exception, commands.MissingPermissions):
            response = _("You do not have enough permissions to do it.").format(
                ctx.author.mention
            )
        elif isinstance(exception, commands.BotMissingPermissions):
            response = _("I do not have enough permissions to do it.")
        elif isinstance(exception, discord.errors.Forbidden):
            response = _("I am missing permissions.")
        elif isinstance(
            exception, (commands.errors.BadArgument, commands.errors.BadUnionArgument)
        ):
            response = _("Arguments specified incorrectly:```diff\n- {0}```").format(
                "\n- ".join(list(exception.args))
            )
        elif isinstance(exception, commands.errors.MissingRequiredArgument):
            response = _("Required arguments not specified.")
            await ctx.send_help()
        elif isinstance(exception, discord.errors.HTTPException):
            response = _("An error occurred while making an HTTP request.")
        elif isinstance(exception, NoPremium):
            response = _("This command is only for premium guilds.")
        elif isinstance(exception, commands.errors.DisabledCommand):
            response = _("Command `{0}` is disabled.").format(
                ctx.command.qualified_name
            )
        if not response:
            if ctx.cog and (
                getattr(Cog, "_get_overridden_method")(ctx.cog.cog_command_error)
                is not None
                or hasattr(ctx.command, "on_error")
            ):
                return
            self.logger.warning(
                f"Ignoring exception in command {ctx.command}: {exception}"
            )
            self.logger.warning(
                "\n".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                )
            )
        else:
            try:
                await ctx.send(response)
            except discord.Forbidden:
                await ctx.author.send(
                    _("I can't send messages to `{0}` channel.").format(
                        ctx.channel.name
                    )
                )

    async def on_guild_post(self):
        self.logger.info("Server count posted successfully")

    # Methods

    async def define_locale(self, obj: Union[discord.Message, Context]):
        if obj.guild:
            guild = await self.db.guilds.find_one(
                {"id": obj.guild.id},
                {
                    "locale": True,
                    "premium": True,
                    "channels": {"$elemMatch": {"id": obj.channel.id}},
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

    def should_reply(self, message):
        """Returns whether the bot should reply to a given message"""
        return not message.author.bot and self.is_ready() and self.launch_time

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
