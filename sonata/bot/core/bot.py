import inspect
from datetime import datetime
from logging import Logger
from typing import Union, Optional

import aiohttp
import discord
from discord.ext import commands
from motor import motor_asyncio as motorio

from sonata.bot.utils import i18n
from .cog import Cog
from .context import Context
from .errors import NoPremium
from .help import HelpCommand


class Sonata(commands.Bot):
    def __init__(
        self,
        default_prefix,
        db: motorio.AsyncIOMotorDatabase,
        config: dict,
        logger: Logger = None,
        *args,
        **kwargs,
    ):
        self.config = config
        super().__init__(
            command_prefix=determine_prefix,
            status=discord.Status.idle,
            help_command=HelpCommand(),
            *args,
            **kwargs,
        )
        self.default_prefix = default_prefix
        self.db = db
        self.logger = logger
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.launch_time = None

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
        return discord.utils.oauth_url(self.user.id, permissions=discord.Permissions(8))

    # Events

    async def on_ready(self):
        self.help_command.cog = self.get_cog("General")
        await self.change_presence(status=discord.Status.dnd)
        if not self.launch_time:
            self.launch_time = datetime.utcnow()
        self.logger.info("Sonata is ready")

    async def on_message(self, message: discord.Message):
        if not self.should_reply(message):
            return

        await self.process_commands(message)

    async def on_command_error(self, ctx: Context, exception: Exception):
        if ctx.cog:
            if getattr(Cog, "_get_overridden_method")(
                ctx.cog.cog_command_error
            ) is not None or hasattr(ctx.command, "on_error"):
                return

        if isinstance(exception, commands.MissingPermissions):
            await ctx.send(
                _("You do not have enough permissions to do it.").format(
                    ctx.author.mention
                )
            )
        elif isinstance(exception, commands.BotMissingPermissions):
            await ctx.send(_("I do not have enough permissions to do it."))
        elif isinstance(exception, discord.errors.Forbidden):
            await ctx.send(_("I am forbidden to do it."))
        elif isinstance(
            exception, (commands.errors.BadArgument, commands.errors.BadUnionArgument)
        ):
            await ctx.send(
                _("Arguments specified incorrectly:```diff\n- {0}```").format(
                    "\n- ".join(list(exception.args))
                )
            )
        elif isinstance(exception, commands.errors.MissingRequiredArgument):
            await ctx.send(_("Required arguments not specified."))
            await ctx.send_help()
        elif isinstance(exception, discord.errors.HTTPException):
            await ctx.send(_("An error occurred while making an HTTP request."))
        elif isinstance(exception, NoPremium):
            await ctx.send(_("This command is only for premium guilds."))
        else:
            self.logger.warning(
                f"Ignoring exception in command {ctx.command}: {exception}"
            )

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
