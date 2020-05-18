import discord
from discord.ext import commands

from .twitch import TwitchMixin
from ... import core


class Streams(TwitchMixin):
    @core.group(invoke_withot_command=True)
    @commands.is_owner()
    async def alerts(self, ctx: core.Context):
        if ctx.invoked_subcommand is not None:
            await ctx.send_help()

    @alerts.command(name="set")
    async def alerts_set(self, ctx: core.Context, channel: discord.TextChannel):
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.inform(_("I can't send messages in this channel."))
        await ctx.db.guilds.update_one(
            {"id": ctx.guild.id}, {"$set": {"alerts.channel": channel.id}}
        )
        await ctx.inform(_("Alerts channels set."))
