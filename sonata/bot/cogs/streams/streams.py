import discord
from discord.ext import commands

from .twitch import TwitchMixin
from ... import core


class Streams(TwitchMixin):
    @core.group()
    @commands.is_owner()
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
        _("""Sets alert settings""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts_set.command(name="channel")
    async def alerts_set_channel(self, ctx: core.Context, channel: discord.TextChannel):
        _(
            """Sets default alert channel
        
        Example
        - alerts set channel @TextChannel"""
        )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.channel": channel.id}}
        )
        await ctx.inform(_("Alerts channels set."))

    @alerts_set.command(name="message")
    async def alerts_set_message(
        self, ctx: core.Context, *, message: commands.clean_content()
    ):
        _(
            """Sets default alert message
        
        Replacements
        {{link}} - stream link
        {{name}} - streamer name
        
        Example
        - alerts set message {{name}} began to stream. Link: {{link}}"""
        )
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.message": message}}
        )
        await ctx.inform(_("Alerts message set."))

    @alerts_set.group(name="embed")
    async def alerts_set_embed(self, ctx: core.Context):
        _("""Enables/Disables sending an alert in an embedded message""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts_set_embed.command(name="enable")
    async def alerts_set_embed_enable(self, ctx: core.Context):
        _("""Enables sending an alert in an embedded message""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.embed": True}}
        )
        await ctx.inform(_("Alerting in the embedded message is enabled."))

    @alerts_set_embed.command(name="disable")
    async def alerts_set_embed_disable(self, ctx: core.Context):
        _("""Disables sending an alert in an embedded message""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.embed": False}}
        )
        await ctx.inform(_("Alerting in the embedded message is disabled."))

    @alerts_set.group(name="mention")
    async def alerts_set_mention(self, ctx: core.Context):
        _("""Enables/Disables alert mentions""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @alerts_set_mention.command(name="everyone")
    async def alerts_set_mention_everyone(self, ctx: core.Context):
        _("""Enables alert everyone mention""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention": "everyone"}}
        )
        await ctx.inform(_("Alerts will mention `everyone`."))

    @alerts_set_mention.command(name="here")
    async def alerts_set_mention_here(self, ctx: core.Context):
        _("""Enables alert here mention""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention": "here"}}
        )
        await ctx.inform(_("Alerts will mention `here`."))

    @alerts_set_mention.command(name="disable")
    async def alerts_set_mention_disable(self, ctx: core.Context):
        _("""Disables alert mentions""")
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.mention": None}}
        )
        await ctx.inform(_("Alert mentions disabled."))
