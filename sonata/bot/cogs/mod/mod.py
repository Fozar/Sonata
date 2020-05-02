import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core


class Mod(core.Cog, colour=discord.Colour(0xD0021B)):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.command()
    @commands.bot_has_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: core.Context,
        members: commands.Greedy[discord.Member],
        reason: clean_content(),
    ):
        if not members:
            return await ctx.send(_("You must specify at least one member."))
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
