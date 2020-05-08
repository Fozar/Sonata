import asyncio
from datetime import timedelta, datetime
from typing import Optional, Union, cast

import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.cogs.mod.modlog import Modlog
from sonata.bot.core import checks
from sonata.bot.utils.converters import ModeratedMember, delete_message_days
from sonata.db.models import ChannelPermissionsCache, ModlogCase

action_opposites = {
    discord.AuditLogAction.ban: discord.AuditLogAction.unban,
    discord.AuditLogAction.overwrite_create: discord.AuditLogAction.overwrite_delete,
}


class Mod(Modlog, colour=discord.Colour(0xD0021B)):
    @core.Cog.listener()
    async def on_modlog_case_expire(self, case: ModlogCase):
        action = discord.AuditLogAction.try_value(case.action)
        opposite_action = action_opposites[action]
        guild = self.sonata.get_guild(case.guild_id) or await self.sonata.fetch_guild(
            case.guild_id
        )
        channel = await self.get_modlog_channel(case.guild_id)
        if channel:
            await self.sonata.set_locale(channel)
        now = datetime.utcnow()
        new_case = ModlogCase(
            created_at=now,
            guild_id=case.guild_id,
            id=discord.utils.time_snowflake(now),
            action=opposite_action.value,
            user_id=case.user_id,
            target_id=case.target_id,
            reason=_("Time expired"),
        )
        if opposite_action == discord.AuditLogAction.unban:
            bans = await guild.bans()
            user = discord.utils.get(bans, user__id=new_case.target_id)
            if user:
                await guild.unban(user.user, reason=new_case.reason)
            else:
                return
        elif opposite_action == discord.AuditLogAction.overwrite_delete:
            member = guild.get_member(new_case.target_id) or guild.fetch_member(
                new_case.target_id
            )
            aws = []
            for ch in guild.channels:
                aws.append(self.unmute_channel(ch, member, reason=new_case.reason))
            await asyncio.gather(*aws)
        embed = await self.make_case_embed(new_case)
        try:
            await channel.send(embed=embed)
            return
        except discord.Forbidden:
            await self.sonata.db.guilds.update_one(
                {"id": case.guild_id}, {"$set": {"modlog": None}}
            )

    async def cog_check(self, ctx: core.Context):
        return ctx.guild

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
                    member,
                    overwrite=cast(discord.PermissionOverwrite, None),
                    reason=reason,
                )
            else:
                await channel.set_permissions(
                    member, overwrite=overwrites, reason=reason
                )
        except discord.Forbidden:
            pass

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

    @core.group(invoke_without_command=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.check_any(commands.has_permissions(ban_members=True), checks.is_mod())
    async def ban(
        self,
        ctx: core.Context,
        member: ModeratedMember(),
        delete_days: Optional[delete_message_days] = 0,
        *,
        reason: clean_content(),
    ):
        _(
            """Ban user in the guild
        
        You can specify number of days worth of messages to delete from the user in the \
        guild. The minimum is 0 and the maximum is 7. Defaults to 0.
        
        Examples:
        - ban @User flood
        - ban User#1234 1 spam
        - ban 239686604271124481 7 bad words"""
        )
        await ctx.guild.ban(member, delete_message_days=delete_days, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("User banned: {0}").format(str(member)))
        await self.create_modlog_case(ctx, member, discord.AuditLogAction.ban, reason)

    @ban.command(name="temp")
    async def ban_temp(
        self,
        ctx: core.Context,
        member: ModeratedMember(),
        delta_seconds: int,
        delete_days: Optional[delete_message_days] = 0,
        *,
        reason: clean_content(),
    ):
        _(
            """Temporarily ban user in the guild

        You can specify number of days worth of messages to delete from the user in the \
        guild. The minimum is 0 and the maximum is 7. Defaults to 0.

        Examples:
        - ban temp @User 60 flood
        - ban temp User#1234 1800 1 spam
        - ban temp 239686604271124481 10 7 bad words"""
        )
        await ctx.guild.ban(member, delete_message_days=delete_days, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("User banned: {0}").format(str(member)))
        await self.create_modlog_case(
            ctx,
            member,
            discord.AuditLogAction.ban,
            reason,
            expires_at=ctx.message.created_at + timedelta(seconds=delta_seconds),
        )

    @core.command()
    @commands.bot_has_permissions(ban_members=True)
    @commands.check_any(commands.has_permissions(ban_members=True), checks.is_mod())
    async def unban(self, ctx: core.Context, user: int, *, reason: clean_content()):
        _(
            """Unban user in the guild
            
        You must provide a user ID.
        
        Examples:
        - unban 239686604271124481 amnesty"""
        )
        bans = await ctx.guild.bans()
        user = discord.utils.get(bans, user__id=user)
        if not user:
            return await ctx.send(_("User not banned."))
        await ctx.guild.unban(user.user, reason=reason)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("User unbanned: {0}").format(str(user)))
        await self.create_modlog_case(ctx, user, discord.AuditLogAction.unban, reason)

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

    @core.group(invoke_without_command=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.check_any(commands.has_permissions(manage_roles=True), checks.is_mod())
    async def mute(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content()
    ):
        _(
            """Mute member in the guild

        Examples:
        - mute @User flood
        - mute User#1234 1 spam
        - mute 239686604271124481 7 bad words"""
        )
        with ctx.typing():
            aws = [
                self.mute_channel(channel, member, reason)
                for channel in ctx.guild.channels
            ]
            await asyncio.gather(*aws)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member muted: {0}").format(str(member)))
        await self.create_modlog_case(
            ctx, member, discord.AuditLogAction.overwrite_create, reason
        )

    @mute.command(name="temp")
    async def mute_temp(
        self,
        ctx: core.Context,
        member: ModeratedMember(),
        delta_seconds: int,
        *,
        reason: clean_content(),
    ):
        _(
            """Temporarily mute member in the guild

        Examples:
        - mute temp @User 60 flood
        - mute temp User#1234 1800 1 spam
        - mute temp 239686604271124481 10 7 bad words"""
        )
        with ctx.typing():
            aws = [
                self.mute_channel(channel, member, reason)
                for channel in ctx.guild.channels
            ]
            await asyncio.gather(*aws)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member muted: {0}").format(str(member)))
        await self.create_modlog_case(
            ctx,
            member,
            discord.AuditLogAction.overwrite_create,
            reason,
            expires_at=ctx.message.created_at + timedelta(seconds=delta_seconds),
        )

    @core.command()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.check_any(commands.has_permissions(manage_roles=True), checks.is_mod())
    async def unmute(
        self, ctx: core.Context, member: ModeratedMember(), *, reason: clean_content()
    ):
        _(
            """Unmute member in the guild

        Examples:
        - unmute @User apologized
        - unmute User#1234 1 amnesty
        - unmute 239686604271124481 7 expired"""
        )
        with ctx.typing():
            aws = []
            for channel in ctx.guild.channels:
                aws.append(self.unmute_channel(channel, member, reason))
            await asyncio.gather(*aws)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(_("Member unmuted: {0}").format(str(member)))
        action = discord.AuditLogAction.overwrite_delete
        await self.sonata.db.modlog_cases.update_many(
            {
                "guild_id": ctx.guild.id,
                "target_id": member.id,
                "action": action.value,
                "expired": False,
            },
            {"$set": {"expired": True}},
        )
        await self.create_modlog_case(ctx, member, action, reason)
