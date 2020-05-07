import asyncio
from typing import Optional, Union, cast

import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.cogs.mod.modlog import Modlog
from sonata.bot.core import checks
from sonata.bot.utils.converters import ModeratedMember
from sonata.db.models import ChannelPermissionsCache


class Mod(Modlog, colour=discord.Colour(0xD0021B)):
    async def cog_check(self, ctx: core.Context):
        return ctx.guild

    @core.command()
    @commands.bot_has_permissions(kick_members=True)
    @commands.check_any(commands.has_permissions(kick_members=True), checks.is_mod())
    async def kick(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content(),
    ):
        _(
            """Kick member from the guild
        
        Examples:
        - kick @Member flood
        - kick Member#1234 spam
        - kick 239686604271124481 bad words"""
        )
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
        member: ModeratedMember(),
        delete_days: Optional[int] = 0,
        *,
        reason: clean_content(),
    ):
        _(
            """Ban user in the guild
        
        You can specify number of days worth of messages to delete from the user in the \
        guild. The minimum is 0 and the maximum is 7. Defaults to 0.
        
        Examples:
        - ban @Member flood
        - ban Member#1234 1 spam
        - ban 239686604271124481 7 bad words"""
        )
        if not 0 <= delete_days <= 7:
            return await ctx.inform(
                _("The minimum deleted days are 0 and the maximum is 7.")
            )
        await ctx.guild.ban(member, delete_message_days=delete_days, reason=reason)
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
        _(
            """Unban user in the guild
        
        Examples:
        - unban @Member conflict resolved
        - unban Member#1234 1 apologized
        - unban 239686604271124481 7 amnesty"""
        )
        await ctx.guild.unban(user, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member unbanned: {0}").format(str(user)))
        await self.create_modlog_case(ctx, user, discord.AuditLogAction.unban, reason)

    async def purge_channel(self, ctx: core.Context, limit, before, reason, check=None):
        if before is not None:
            if before.channel != ctx.channel:
                return await ctx.inform(
                    _("`Before` message must be in the same channel.")
                )
            before = before.created_at
        await ctx.channel.purge(limit=limit, before=before, check=check)
        await self.create_modlog_case(
            ctx, ctx.channel, discord.AuditLogAction.message_bulk_delete, reason
        )

    @core.group(aliases=["clear"], invoke_without_command=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.check_any(commands.has_permissions(manage_messages=True), checks.is_mod())
    async def purge(
        self,
        ctx: core.Context,
        limit: int,
        before: Optional[discord.Message] = None,
        *,
        reason: clean_content(),
    ):
        _(
            """Purges messages in the channel
        
        You can specify message before which to start purging. The message must be in \
        the same channel.
        
        Examples:
        - purge 10 flood
        - purge 20 706903341934051489 spam
        - purge 100 <message url> raid"""
        )
        await self.purge_channel(ctx, limit, before, reason)

    @purge.command(name="bot")
    async def purge_bot(
        self,
        ctx: core.Context,
        limit: int,
        before: Optional[discord.Message] = None,
        *,
        reason: clean_content(),
    ):
        _("""Purges bot's messages in the channel""")
        await self.purge_channel(
            ctx, limit, before, reason, check=lambda m: m.author == ctx.guild.me
        )

    async def mute_channel(
        self,
        channel: Union[
            discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel
        ],
        member: discord.Member,
        reason: str,
    ):
        overwrites = channel.overwrites_for(member)
        new_overs = {}
        if not isinstance(channel, discord.TextChannel):
            new_overs.update(speak=False)
        if not isinstance(channel, discord.VoiceChannel):
            new_overs.update(send_messages=False, add_reactions=False)
        old_overs = {k: getattr(overwrites, k) for k in new_overs}
        overwrites.update(**new_overs)
        try:
            await channel.set_permissions(member, overwrite=overwrites, reason=reason)
        except discord.Forbidden:
            return
        cache = ChannelPermissionsCache(
            guild_id=channel.guild.id,
            channel_id=channel.id,
            member_id=member.id,
            value=old_overs,
        ).dict()
        await self.sonata.db.channel_perms_cache.insert_one(cache)

    async def unmute_channel(
        self,
        channel: Union[
            discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel
        ],
        member: discord.Member,
        reason: str,
    ):
        overwrites = channel.overwrites_for(member)
        perms_cache = await self.sonata.db.channel_perms_cache.find_one_and_delete(
            {
                "guild_id": channel.guild.id,
                "channel_id": channel.id,
                "member_id": member.id,
            },
            {"value": True},
        )

        if perms_cache:
            old_values = perms_cache["value"]
        else:
            old_values = {"send_messages": None, "add_reactions": None, "speak": None}

        overwrites.update(**old_values)
        try:
            if overwrites.is_empty():
                await channel.set_permissions(
                    member, overwrite=cast(discord.PermissionOverwrite, None), reason=reason
                )
            else:
                await channel.set_permissions(member, overwrite=overwrites, reason=reason)
        except discord.Forbidden:
            pass

    @core.command()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.check_any(commands.has_permissions(manage_roles=True), checks.is_mod())
    async def mute(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content()
    ):
        with ctx.typing():
            aws = []
            for channel in ctx.guild.channels:
                aws.append(self.mute_channel(channel, member, reason))
            await asyncio.gather(*aws)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member muted: {0}").format(str(member)))
        await self.create_modlog_case(
            ctx, member, discord.AuditLogAction.overwrite_create, reason
        )

    @core.command()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.check_any(commands.has_permissions(manage_roles=True), checks.is_mod())
    async def unmute(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content()
    ):
        with ctx.typing():
            aws = []
            for channel in ctx.guild.channels:
                aws.append(self.unmute_channel(channel, member, reason))
            await asyncio.gather(*aws)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member unmuted: {0}").format(str(member)))
        await self.create_modlog_case(
            ctx, member, discord.AuditLogAction.overwrite_delete, reason
        )
