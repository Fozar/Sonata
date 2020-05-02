import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.utils import ModeratedMember


class Mod(core.Cog, colour=discord.Colour(0xD0021B)):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def cog_check(self, ctx: core.Context):
        return ctx.guild

    @core.command()
    @commands.bot_has_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: core.Context,
        members: commands.Greedy[ModeratedMember()],
        reason: clean_content(),
    ):
        _("""Kick members from the guild.""")
        if not members:
            return await ctx.inform(_("You must specify at least one member."))

        for member in members:
            await member.kick(reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(
                _("Members kicked out: {0}").format(
                    ", ".join([str(member) for member in members])
                )
            )
