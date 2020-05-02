import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.utils.converters import ModeratedMember


class Mod(core.Cog, colour=discord.Colour(0xD0021B)):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def cog_check(self, ctx: core.Context):
        return ctx.guild

    @core.command()
    @commands.bot_has_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content(),
    ):
        _("""Kick member from the guild.""")

        await member.kick(reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member kicked out: {0}").format(str(member)))
