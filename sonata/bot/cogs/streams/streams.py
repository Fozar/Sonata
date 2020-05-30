import discord
from discord.ext import commands

from .twitch import TwitchMixin
from ... import core


class Streams(TwitchMixin, colour=discord.Colour.dark_orange()):
    async def cog_check(self, ctx: core.Context):
        return ctx.guild

    @core.group()
    @commands.has_guild_permissions(manage_messages=True)
    async def alerts(self, ctx: core.Context):
        _("""Alerts settings""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts.command(name="enable")
    async def alerts_enable(self, ctx: core.Context):
        _("""Enables alerts""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.enabled": True}}
        )
        await ctx.inform(_("Alerts enabled."))

    @alerts.command(name="disable")
    async def alerts_disable(self, ctx: core.Context):
        _("""Disables alerts""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.enabled": False}}
        )
        await ctx.inform(_("Alerts disabled."))

    @alerts.group(name="set")
    async def alerts_set(self, ctx: core.Context):
        _("""Sets default alert settings""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts_set.command(name="channel")
    async def alerts_set_channel(self, ctx: core.Context, channel: discord.TextChannel):
        _(
            """Sets default alert channel
        
        Example
        - alerts set channel #TextChannel"""
        )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.channel": channel.id}}
        )
        await ctx.inform(_("Alerts channel set."))

    @alerts_set.command(name="offline.message")
    async def alerts_set_close_message(
        self, ctx: core.Context, *, message: commands.clean_content()
    ):
        _(
            """Sets default offline alert message

        Markdown is allowed.

        Replacements
        {{link}} - stream link
        {{name}} - streamer name
        {{views}} - user's views count

        Example
        - alerts set offline.message {{name}} if offline."""
        )
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.close_message": message}}
        )
        await ctx.inform(_("Alerts offline message set."))

    @alerts_set.command(name="message")
    async def alerts_set_message(
        self, ctx: core.Context, *, message: commands.clean_content()
    ):
        _(
            """Sets default alert message
            
        Markdown is allowed.
        
        Replacements
        {{link}} - stream link
        {{name}} - streamer name
        {{title}} - stream title
        {{game}} - game name
        {{viewers}} - viewers count
        {{views}} - user's views count
        
        Example
        - alerts set message {{name}} began broadcasting "{{game}}". Link: {{link}}"""
        )
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.message": message}}
        )
        await ctx.inform(_("Alerts message set."))

    @alerts_set.group(name="mention")
    async def alerts_set_mention(self, ctx: core.Context):
        _("""Toggles alert mentions""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts_set_mention.command(name="everyone")
    async def alerts_set_mention_everyone(self, ctx: core.Context):
        _(
            """Sets alert mentions to `@everyone`
        
        The bot must have the permission to mention everyone."""
        )
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention.value": "everyone"}}
        )
        await ctx.inform(_("Alerts will mention `@everyone`."))

    @alerts_set_mention.command(name="here")
    async def alerts_set_mention_here(self, ctx: core.Context):
        _(
            """Sets alert mentions to `@here`
        
        The bot must have the permission to mention everyone."""
        )
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention.value": "here"}}
        )
        await ctx.inform(_("Alerts will mention `@here`."))

    @alerts_set_mention.command(name="enable")
    async def alerts_set_mention_enable(self, ctx: core.Context):
        _("""Enables alert mentions""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention.enabled": True}}
        )
        await ctx.inform(_("Alert mentions enabled."))

    @alerts_set_mention.command(name="disable")
    async def alerts_set_mention_disable(self, ctx: core.Context):
        _("""Disables alert mentions""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention.enabled": False}}
        )
        await ctx.inform(_("Alert mentions disabled."))
