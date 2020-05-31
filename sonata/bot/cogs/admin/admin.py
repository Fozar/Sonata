import discord
from babel import Locale
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.utils.converters import (
    to_lower,
    locale_to_flag,
    validate_locale,
)
from sonata.db.models import Channel, Greeting, BWList, Guild


class Admin(
    core.Cog,
    description=_(
        "This module is responsible for the unique behavior of the bot in your guild. "
        "You can disable and enable modules and commands, change the language and prefix "
        "of the bot and so on"
    ),
    colour=discord.Colour.dark_orange(),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def cog_check(self, ctx: core.Context):
        if not ctx.guild:
            return False
        if ctx.author.guild_permissions.administrator or await self.sonata.is_owner(
            ctx.author
        ):
            return True
        guild = await ctx.db.guilds.find_one(
            {"id": ctx.guild.id}, {"admin_roles": True}
        )
        if (
            guild
            and guild.get("admin_roles")
            and discord.utils.find(
                lambda role: role.id in guild["admin_roles"], ctx.author.roles
            )
            is not None
        ):
            return True
        return False

    # Events

    @core.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = await self.sonata.db.guilds.find_one(
            {"id": member.guild.id}, {"_id": False, "greeting": True}
        )
        if not guild or not guild.get("greeting"):
            return

        greeting = guild["greeting"]
        channel = discord.utils.get(
            member.guild.text_channels, id=greeting["channel_id"]
        )
        if channel is None:
            return

        msg = (
            greeting["message"]
            .replace("[member]", member.display_name)
            .replace("[mention]", member.mention)
        )
        await channel.send(msg)

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
        self,
        ctx: core.Context,
        channel: discord.TextChannel,
        locale: validate_locale = None,
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
            ctx.locale = locale
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

    @guild.group(name="auto-message", aliases=["automsg"])
    async def guild_auto_message(self, ctx: core.Context):
        _("""Disables/Enables auto-message when leveling up for all members""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @guild_auto_message.command(name="enable", aliases=["on"])
    async def guild_auto_message_enable(self, ctx: core.Context):
        _("""Enables auto-message when leveling up for all members""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"auto_lvl_msg": True}}
        )
        if result.modified_count == 0:
            await ctx.inform(
                _("Auto-message when leveling up is already enabled for all members.")
            )
        else:
            await ctx.inform(
                _("Auto-message when leveling up is enabled for all members.")
            )

    @guild_auto_message.command(name="disable", aliases=["off"])
    async def guild_auto_message_disable(self, ctx: core.Context):
        _("""Disables auto-message when leveling up for all members""")
        result = await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"auto_lvl_msg": False}}
        )
        if result.modified_count == 0:
            await ctx.inform(
                _("Auto-message when leveling up is already disabled for all members.")
            )
        else:
            await ctx.inform(
                _("Auto-message when leveling up is disabled for all members.")
            )

    @guild.group(name="blacklist", aliases=["bl"], invoke_without_command=True)
    async def guild_blacklist(self, ctx: core.Context):
        _(
            """Guild blacklist

        The bot will not respond to commands in blacklisted channels."""
        )
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"blacklist": True})
        blacklist = guild.get("blacklist")
        if blacklist is None:
            return await ctx.inform(_("Blacklist is empty."))

        channels_id = blacklist.get("items")
        embed = discord.Embed(colour=self.colour, title=_("Blacklist"))
        try:
            channels = [ctx.guild.get_channel(ch) for ch in channels_id]
            mentions = [ch.mention for ch in channels if ch is not None]
            if not mentions:
                raise TypeError
            embed.description = _("**Channels**\n") + ", ".join(mentions)
        except TypeError:
            return await ctx.inform(_("Blacklist is empty."))
        await ctx.send(embed=embed)

    @guild_blacklist.command(name="add")
    async def guild_blacklist_add(
        self, ctx: core.Context, channels: commands.Greedy[discord.TextChannel]
    ):
        _("""Adds channels to blacklist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id},
            {
                "$addToSet": {
                    "blacklist.items": {"$each": [ch.id for ch in channels]}
                }
            },
        )
        await ctx.inform(_("Channels successfully added to blacklist."))

    @guild_blacklist.command(name="clear")
    async def guild_blacklist_clear(self, ctx: core.Context):
        _("""Clears the blacklist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"blacklist": BWList().dict()}}
        )
        await ctx.inform(_("Blacklist cleared successfully."))

    @guild_blacklist.command(name="disable")
    async def guild_blacklist_disable(self, ctx: core.Context):
        _("""Disables blacklist in the guild""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"blacklist.enabled": False}},
        )
        await ctx.inform(_("Blacklist disabled."))

    @guild_blacklist.command(name="enable")
    async def guild_blacklist_enable(self, ctx: core.Context):
        _("""Enables blacklist in the guild""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"blacklist.enabled": True}},
        )
        await ctx.inform(_("Blacklist enabled."))

    @guild_blacklist.command(name="remove")
    async def guild_blacklist_remove(
        self, ctx: core.Context, channels: commands.Greedy[discord.TextChannel]
    ):
        _("""Removes channels from blacklist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id},
            {"$pull": {"blacklist.items": {"$in": [ch.id for ch in channels]}}},
        )
        await ctx.inform(_("Channels successfully removed from blacklist."))

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

    @guild.group(name="greeting", aliases=["welcome"])
    async def guild_greeting(self, ctx: core.Context):
        _("""Welcome message""")
        if ctx.invoked_subcommand is not None:
            return

        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"greeting": True})
        if not guild.get("greeting"):
            return await ctx.inform(_("Welcome message not set."))

        greeting = guild["greeting"]
        channel = discord.utils.get(ctx.guild.text_channels, id=greeting["channel_id"])
        if channel is None:
            return await ctx.inform(_("Channel not found. Set a new welcome message."))

        await ctx.inform(
            _("**Channel**: {channel}\n**Message**: ```{msg}```").format(
                channel=channel.mention, msg=greeting["message"]
            )
        )

    @guild_greeting.command(name="disable")
    async def guild_greeting_disable(self, ctx: core.Context):
        _("""Disables the greeting message.""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"greeting": None}}
        )
        await ctx.inform(_("Welcome message is disabled."))

    @guild_greeting.command(name="set")
    async def guild_greeting_set(
        self,
        ctx: core.Context,
        channel: discord.TextChannel,
        *,
        message: clean_content()
    ):
        _(
            """Sets welcome message

        Use [member] to display the member name in the message or [mention] to @mention.
        Example:
        - guild greeting set #channel Hi, [member]! Welcome to our guild!"""
        )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))
        if len(message) > 2000:
            return await ctx.inform(_("Welcome message cannot exceed 2000 characters."))

        greeting = Greeting(channel_id=channel.id, message=message).dict()
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"greeting": greeting}}
        )
        await ctx.inform(_("Welcome message set."))

    @guild.command(name="locale")
    async def guild_locale(self, ctx: core.Context, locale: validate_locale = None):
        _("""Set guild locale""")
        if locale is None:
            guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"locale": True})
            return await ctx.inform(
                _("Current guild locale is {flag} `{locale}`.").format(
                    flag=locale_to_flag(guild["locale"]),
                    locale=Locale.parse(guild["locale"], sep="_").display_name,
                )
            )

        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"locale": locale}}
        )
        ctx.locale = locale
        await ctx.inform(
            _("The guild locale is set to {flag} `{locale}`.").format(
                flag=locale_to_flag(locale), locale=locale,
            )
        )

    @guild.group(name="modlog", invoke_without_command=True)
    async def guild_modlog(self, ctx: core.Context, channel: discord.TextChannel):
        _("""Set modlog channel""")
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))

        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"modlog": channel.id}}
        )
        await ctx.inform(_("Modlog channel is set to {0}.").format(channel.mention))

    @guild_modlog.command(name="reset")
    async def guild_modlog_reset(self, ctx: core.Context):
        _("""Reset modlog channel""")
        await ctx.db.guilds.update_one({"id": ctx.guild.id}, {"$set": {"modlog": None}})
        await ctx.inform(_("Modlog channel reset."))

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

        max_len = 4
        if len(prefix) > max_len:
            return await ctx.inform(
                _(
                    "This prefix is too long. "
                    "The prefix cannot consist of more than {0} characters."
                ).format(max_len)
            )

        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"custom_prefix": prefix}}
        )
        await ctx.inform(_("The guild prefix is set to `{0}`.").format(prefix))

    @guild.command(name="reset")
    async def guild_reset(self, ctx: core.Context):
        _("""Resets guild settings""")
        msg, resp = await ctx.confirm(_("Are you sure?"))
        if not resp:
            return

        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"_id": False})
        new_guild = Guild(
            id=guild["id"],
            name=guild["name"],
            premium=guild["premium"],
            created_at=guild["created_at"],
            last_message_at=guild["last_message_at"],
            owner_id=guild["owner_id"],
        ).dict()
        await ctx.db.guilds.update_one({"id": ctx.guild.id}, {"$set": new_guild})
        await ctx.inform(_("Guild settings reset."))

    @guild.group(name="role")
    async def guild_role(self, ctx: core.Context):
        _("""Set privileged roles""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @guild_role.group(name="admin", invoke_without_command=True)
    async def guild_role_admin(self, ctx: core.Context):
        _(
            """Admin roles
        
        Members who have the at least one of admin roles can use Admin cog on a par \
        with members who have administrator permissions."""
        )
        guild = await ctx.db.guilds.find_one(
            {"id": ctx.guild.id}, {"admin_roles": True}
        )
        if not guild or not guild.get("admin_roles"):
            return await ctx.inform(_("Admin roles not set."))

        roles = []
        for role_id in guild["admin_roles"]:
            role = ctx.guild.get_role(role_id)
            if role is None:
                await ctx.db.guilds.update_one(
                    {"id": ctx.guild.id}, {"$pull": {"admin_roles": role_id}}
                )
            else:
                roles.append(role)
        await ctx.inform(
            _("Admin roles: {0}.").format(", ".join([str(role) for role in roles]))
        )

    @guild_role_admin.command(name="add")
    async def guild_role_admin_add(
        self, ctx: core.Context, roles: commands.Greedy[discord.Role]
    ):
        _(
            """Add roles to admin role list
            
        You can specify roles using the ID, mention, or name of the role.
        
        Examples:
        - guild role admin add @Admin
        - guild role admin add @MiniAdmin @Admin @BotManager
        - guild role admin add 705363996747759657 Admin"""
        )
        if not roles:
            return await ctx.inform(_("You must specify at least one role."))
        role_ids = [role.id for role in roles]
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$addToSet": {"admin_roles": {"$each": role_ids}}}
        )
        await ctx.inform(_("Roles successfully added."))

    @guild_role_admin.command(name="remove")
    async def guild_role_admin_remove(
        self, ctx: core.Context, roles: commands.Greedy[discord.Role]
    ):
        _(
            """Removes roles from admin role list
        
        You can specify roles using the ID, mention, or name of the role.
        
        Examples:
        - guild role admin remove @Admin
        - guild role admin remove @MiniAdmin @Admin @BotManager
        - guild role admin remove 705363996747759657 Admin"""
        )
        if not roles:
            return await ctx.inform(_("You must specify at least one role."))
        role_ids = [role.id for role in roles]
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$pull": {"admin_roles": {"$in": role_ids}}}
        )
        await ctx.inform(_("Roles successfully removed."))

    @guild_role.group(name="mod", invoke_without_command=True)
    async def guild_role_mod(self, ctx: core.Context):
        _(
            """Mod roles

        Members who have the at least one of mod roles can use Mod cog without having \
        to have the appropriate permissions."""
        )
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"mod_roles": True})
        if not guild or not guild.get("mod_roles"):
            return await ctx.inform(_("Mod roles not set."))

        roles = []
        for role_id in guild["mod_roles"]:
            role = ctx.guild.get_role(role_id)
            if role is None:
                await ctx.db.guilds.update_one(
                    {"id": ctx.guild.id}, {"$pull": {"mod_roles": role_id}}
                )
            else:
                roles.append(role)
        await ctx.inform(
            _("Mod roles: {0}.").format(", ".join([str(role) for role in roles]))
        )

    @guild_role_mod.command(name="add")
    async def guild_role_mod_add(
        self, ctx: core.Context, roles: commands.Greedy[discord.Role]
    ):
        _(
            """Add roles to mod role list

        You can specify roles using the ID, mention, or name of the role.

        Examples:
        - guild role mod add @Mod
        - guild role mod add @MiniMod @Mod
        - guild role mod add 705363996747759657 Mod"""
        )
        if not roles:
            return await ctx.inform(_("You must specify at least one role."))
        role_ids = [role.id for role in roles]
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$addToSet": {"mod_roles": {"$each": role_ids}}}
        )
        await ctx.inform(_("Roles successfully added."))

    @guild_role_mod.command(name="remove")
    async def guild_role_mod_remove(
        self, ctx: core.Context, roles: commands.Greedy[discord.Role]
    ):
        _(
            """Removes roles from mod role list

        You can specify roles using the ID, mention, or name of the role.

        Examples:
        - guild role mod remove @Mod
        - guild role mod remove @MiniMod @Mod
        - guild role mod remove 705363996747759657 Mod"""
        )
        if not roles:
            return await ctx.inform(_("You must specify at least one role."))
        role_ids = [role.id for role in roles]
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$pull": {"mod_roles": {"$in": role_ids}}}
        )
        await ctx.inform(_("Roles successfully removed."))

    @guild.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def guild_whitelist(self, ctx: core.Context):
        _(
            """Guild whitelist

        The bot will respond to commands only in whitelisted channels."""
        )
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"whitelist": True})
        whitelist = guild.get("whitelist")
        if not whitelist:
            return await ctx.inform(_("Whitelist is empty."))

        channels_id = whitelist.get("items")
        embed = discord.Embed(colour=self.colour, title=_("Whitelist"))
        try:
            channels = [ctx.guild.get_channel(ch) for ch in channels_id]
            mentions = [ch.mention for ch in channels if ch is not None]
            if not mentions:
                raise TypeError
            embed.description = _("**Channels**\n") + ", ".join(mentions)
        except TypeError:
            return await ctx.inform(_("Whitelist is empty."))
        await ctx.send(embed=embed)

    @guild_whitelist.command(name="add")
    async def guild_whitelist_add(
        self, ctx: core.Context, channels: commands.Greedy[discord.TextChannel]
    ):
        _("""Adds channels to whitelist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id},
            {
                "$addToSet": {
                    "whitelist.items": {"$each": [ch.id for ch in channels]}
                }
            },
        )
        await ctx.inform(_("Channels successfully added to whitelist."))

    @guild_whitelist.command(name="clear")
    async def guild_whitelist_clear(self, ctx: core.Context):
        _("""Clears the whitelist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"whitelist": BWList().dict()}}
        )
        await ctx.inform(_("Whitelist cleared successfully."))

    @guild_whitelist.command(name="disable")
    async def guild_whitelist_disable(self, ctx: core.Context):
        _("""Disables whitelist in the guild""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"whitelist.enabled": False}},
        )
        await ctx.inform(_("Whitelist disabled"))

    @guild_whitelist.command(name="enable")
    async def guild_whitelist_enable(self, ctx: core.Context):
        _("""Enables whitelist in the guild""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"whitelist.enabled": True}},
        )
        await ctx.inform(_("Whitelist enabled."))

    @guild_whitelist.command(name="remove")
    async def guild_whitelist_remove(
        self, ctx: core.Context, channels: commands.Greedy[discord.TextChannel]
    ):
        _("""Removes channels from whitelist""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id},
            {"$pull": {"whitelist.items": {"$in": [ch.id for ch in channels]}}},
        )
        await ctx.inform(_("Channels successfully removed from whitelist."))
