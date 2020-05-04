from typing import Optional, Union

import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.cogs.mod.modlog import Modlog
from sonata.bot.core import checks
from sonata.bot.utils.converters import ModeratedMember


class Mod(Modlog, colour=discord.Colour(0xD0021B)):
    async def cog_check(self, ctx: core.Context):
        return ctx.guild

    @core.command()
    @commands.bot_has_permissions(kick_members=True)
    @commands.check_any(commands.has_permissions(kick_members=True), checks.is_mod())
    async def kick(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content(),
    ):
        _("""Kick member from the guild.""")

        await member.kick(reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member kicked: {0}").format(str(member)))
        await self.create_modlog_case(ctx, member, discord.AuditLogAction.kick, reason)

    @core.command()
    @commands.bot_has_permissions(ban_members=True)
    @commands.check_any(commands.has_permissions(ban_members=True), checks.is_mod())
    async def ban(
        self,
        ctx: core.Context,
        member: Union[ModeratedMember(), discord.User],
        delete_days: Optional[int] = 0,
        *,
        reason: clean_content(),
    ):
        await member.ban(delete_message_days=delete_days, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member banned: {0}").format(str(member)))
        await self.create_modlog_case(ctx, member, discord.AuditLogAction.ban, reason)

    @core.command()
    @commands.bot_has_permissions(ban_members=True)
    @commands.check_any(commands.has_permissions(ban_members=True), checks.is_mod())
    async def unban(
        self, ctx: core.Context, user: discord.User, *, reason: clean_content()
    ):
        await ctx.guild.unban(user, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member unbanned: {0}").format(str(user)))
        await self.create_modlog_case(ctx, user, discord.AuditLogAction.unban, reason)
