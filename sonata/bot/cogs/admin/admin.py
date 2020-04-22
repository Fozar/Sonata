import discord
from babel import Locale

from sonata.bot import core
from sonata.bot.utils import i18n
from sonata.bot.utils.misc import to_lower, make_locale_list, locale_to_flag
from sonata.db.models import Channel, Guild


class Admin(
    core.Cog,
    description=_("""Commands of guild admins"""),
    colour=discord.Colour(0x8B572A),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def cog_check(self, ctx: core.Context):
        return (
            ctx.guild
            and ctx.author.guild_permissions.administrator
            or await self.sonata.is_owner(ctx.author)
        )

    # CHANNELS SETTINGS. PREMIUM ONLY

    @core.group()
    @core.premium_only()
    async def channel(self, ctx: core.Context):
        _("""Channels settings""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @channel.command(name="locale")
    async def channel_locale(
        self, ctx: core.Context, channel: discord.TextChannel, locale: str = None,
    ):
        _("""Set channel locale""")
        if locale is None:
            guild = await ctx.db.guilds.find_one(
                {"id": ctx.guild.id},
                {"locale": True, "channels": {"$elemMatch": {"id": channel.id}}},
            )
            if "channels" in guild:
                locale = guild["channels"][0]["locale"]
            else:
                locale = guild["locale"]

            return await ctx.inform(
                _("Current channel locale is {flag} `{locale}`.").format(
                    flag=locale_to_flag(locale),
                    locale=Locale.parse(locale, sep="_").display_name,
                )
            )

        if locale not in i18n.gettext_translations.keys():
            return await ctx.inform(
                _("I don't speak this language. Available locales: {0}.").format(
                    ", ".join(make_locale_list())
                )
            )

        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id, "channels": {"$elemMatch": {"id": channel.id}}},
            {"$set": {"channels.$.locale": locale}},
        )
        if result.matched_count == 0:
            channel_conf = Channel(
                id=channel.id, name=channel.name, locale=locale
            ).dict()
            await ctx.db.guilds.update_one(
                {"id": ctx.guild.id}, {"$push": {"channels": channel_conf}}
            )
        if channel == ctx.channel:
            i18n.current_locale.set(locale)
        await ctx.inform(
            _("The channel locale is set to {flag} `{locale}`.").format(
                flag=locale_to_flag(locale), locale=locale,
            )
        )

    # GUILD SETTINGS

    @core.group()
    async def guild(self, ctx: core.Context):
        _("""Guild settings""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @guild.group(name="dmhelp")
    async def guild_dmhelp(self, ctx: core.Context):
        _("""Toggle whether to send help message to direct messages""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @guild_dmhelp.command(name="enable")
    async def guild_dmhelp_enable(self, ctx: core.Context):
        _("""Enables sending help to direct messages""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"dm_help": True}}
        )
        if result.modified_count == 0:
            await ctx.inform(
                _("Sending bot help messages to direct messages is already enabled.")
            )
        else:
            await ctx.inform(
                _("Sending bot help messages to direct messages is enabled.")
            )

    @guild_dmhelp.command(name="disable")
    async def guild_dmhelp_disable(self, ctx: core.Context):
        _("""Disables sending help to direct messages""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"dm_help": False}}
        )
        if result.modified_count == 0:
            await ctx.inform(
                _("Sending bot help messages to direct messages is already disabled.")
            )
        else:
            await ctx.inform(
                _("Sending bot help messages to direct messages is disabled.")
            )

    @guild.group(name="cog")
    async def guild_cog(self, ctx: core.Context):
        _("""Disables/Enables cog in the guild""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @guild_cog.command(name="enable")
    async def guild_cog_enable(self, ctx: core.Context, cog: str):
        _("""Enables cog in the guild""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$pull": {"disabled_cogs": cog}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("This cog has not been disabled."))
        else:
            await ctx.inform(_("Cog `{0}` enabled.").format(cog))

    @guild_cog.command(name="disable")
    async def guild_cog_disable(self, ctx: core.Context, cog: str):
        _("""Disables cog in the guild""")
        if cog not in self.sonata.config["bot"].cogs:
            return await ctx.inform(
                _(
                    "Cog `{cog}` does not exist.\n"
                    "You can disable the following cogs: {cogs}."
                ).format(cog=cog, cogs=", ".join(self.sonata.config["bot"].other_cogs))
            )
        if cog in self.sonata.config["bot"].core_cogs:
            return await ctx.inform(_("Cog `{0}` cannot be disabled.").format(cog))
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$addToSet": {"disabled_cogs": cog}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("This cog is already disabled."))
        else:
            await ctx.inform(_("Cog `{0}` disabled.").format(cog))

    @guild.group(name="command")
    async def guild_command(self, ctx: core.Context):
        _("""Disables/Enables command in the guild""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @guild_command.command(name="enable")
    async def guild_command_enable(self, ctx: core.Context, *, command: to_lower):
        _("""Enables command in the guild""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$pull": {"disabled_commands": command}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("This command has not been disabled."))
        else:
            await ctx.inform(_("Command `{0}` enabled.").format(command))

    @guild_command.command(name="disable")
    async def guild_command_disable(self, ctx: core.Context, *, command: to_lower):
        _("""Disables command in the guild""")
        cmd = self.sonata.get_command(command)
        if cmd is None:
            return await ctx.inform(_("Command `{0}` not found.").format(cmd))

        cmd_name = cmd.qualified_name
        if cmd.cog.qualified_name in self.sonata.config["bot"].core_cogs:
            return await ctx.inform(
                _("Command `{0}` cannot be disabled.").format(cmd_name)
            )
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$addToSet": {"disabled_commands": command}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("This command is already disabled."))
        else:
            await ctx.inform(_("Command `{0}` disabled.").format(command))

    @guild.command(name="locale")
    async def guild_locale(self, ctx: core.Context, locale: str = None):
        _("""Set guild locale""")
        if locale is None:
            guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"locale": True})
            return await ctx.inform(
                _("Current guild locale is {flag} `{locale}`.").format(
                    flag=locale_to_flag(guild["locale"]),
                    locale=Locale.parse(guild["locale"], sep="_").display_name,
                )
            )

        if locale not in i18n.gettext_translations.keys():
            return await ctx.inform(
                _("Locale not found. Available locales: {0}.").format(
                    ", ".join(make_locale_list())
                )
            )

        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"locale": locale}}
        )
        i18n.current_locale.set(locale)
        await ctx.inform(
            _("The guild locale is set to {flag} `{locale}`.").format(
                flag=locale_to_flag(locale), locale=locale,
            )
        )

    @guild.command(name="prefix")
    async def guild_prefix(self, ctx: core.Context, prefix: str = None):
        _(
            """Set guild prefix
        
        The guild prefix overwrites the default prefix."""
        )
        if prefix is None:
            guild = await ctx.db.guilds.find_one(
                {"id": ctx.guild.id}, {"custom_prefix": True}
            )
            prefix = guild["custom_prefix"] or ctx.prefix
            return await ctx.inform(_("Current guild prefix is `{0}`.").format(prefix))

        max_len = 3
        if len(prefix) > max_len:
            return await ctx.inform(
                _(
                    "This prefix is too long. The prefix cannot consist of more than {0} characters."
                ).format(max_len)
            )

        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"custom_prefix": prefix}}
        )
        await ctx.inform(_("The guild prefix is set to `{0}`.").format(prefix))

    @guild.command(name="reset")
    async def guild_reset(self, ctx: core.Context):
        _("""Resets guild settings""")  # TODO: Are u sure?
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"_id": False})
        new_guild = Guild(
            id=guild["id"],
            name=guild["name"],
            premium=guild["premium"],
            total_messages=guild["total_messages"],
            commands_invoked=guild["commands_invoked"],
            created_at=guild["created_at"],
            last_message_at=guild["last_message_at"],
        ).dict()
        await ctx.db.guilds.update_one({"id": ctx.guild.id}, {"$set": new_guild})
        await ctx.inform(_("Guild settings reset."))
