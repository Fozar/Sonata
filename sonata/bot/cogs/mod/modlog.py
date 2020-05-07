import asyncio
from datetime import datetime, timedelta
from typing import Union

import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.core import checks
from sonata.bot.utils.converters import ModlogCaseConverter
from sonata.db.models import ModlogCase


class Modlog(core.Cog):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.Cog.listener()
    async def on_modlog_case(self, case: ModlogCase):
        channel = await self.get_modlog_channel(case.guild_id)
        if not channel:
            return
        await self.sonata.db.modlog_cases.insert_one(case.dict())
        await self.sonata.set_locale(channel)
        embed = await self.make_case_embed(case)
        await channel.send(embed=embed)

    @core.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User]
    ):
        case = await self.fetch_modlog_case(guild, user, discord.AuditLogAction.ban)
        if case:
            self.sonata.dispatch("modlog_case", case)

    @core.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        case = await self.fetch_modlog_case(
            member.guild, member, discord.AuditLogAction.kick
        )
        if case:
            self.sonata.dispatch("modlog_case", case)

    @core.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        case = await self.fetch_modlog_case(guild, user, discord.AuditLogAction.unban)
        if case:
            self.sonata.dispatch("modlog_case", case)

    async def get_modlog_channel(self, guild_id: int):
        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": guild_id}, {"modlog": True}
        )
        if not guild_conf or not guild_conf.get("modlog"):
            return None
        try:
            channel = self.sonata.get_channel(
                guild_conf["modlog"]
            ) or await self.sonata.fetch_channel(guild_conf["modlog"])
        except discord.NotFound:
            return None
        else:
            return channel

    async def fetch_modlog_case(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User], action
    ):
        if not guild.me.guild_permissions.view_audit_log:
            return None

        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": guild.id}, {"modlog": True}
        )
        if not guild_conf or not guild_conf.get("modlog", False):
            return None
        now = datetime.utcnow()
        before = now + timedelta(minutes=1)
        after = now - timedelta(minutes=1)
        await asyncio.sleep(10)
        entry = await guild.audit_logs(action=action, before=before, after=after).find(
            lambda e: e.target.id == user.id and after < e.created_at < before
        )
        if not entry or entry.user.id == guild.me.id:
            return None

        return ModlogCase(
            created_at=entry.created_at,
            guild_id=guild.id,
            id=entry.id,
            action=entry.action.value,
            user_id=entry.user.id,
            target_id=entry.target.id,
            reason=entry.reason,
        )

    async def make_case_embed(self, case: ModlogCase):
        action_mapping = {
            discord.AuditLogAction.kick: _("Member kicked"),
            discord.AuditLogAction.ban: _("User banned"),
            discord.AuditLogAction.unban: _("User unbanned"),
            discord.AuditLogAction.message_bulk_delete: _("Messages purged"),
            discord.AuditLogAction.overwrite_create: _("Member muted"),
            discord.AuditLogAction.overwrite_delete: _("Member unmuted"),
        }
        action = discord.AuditLogAction.try_value(case.action)
        embed = discord.Embed(
            colour=self.colour, title=action_mapping[action], timestamp=case.created_at,
        )
        try:
            target = self.sonata.get_user(
                case.target_id
            ) or await self.sonata.fetch_user(case.target_id)
        except discord.NotFound:
            target = None
        if target is None:
            try:
                target = self.sonata.get_channel(
                    case.target_id
                ) or await self.sonata.fetch_channel(case.target_id)
            except discord.NotFound:
                target = None
        if isinstance(target, (discord.User, discord.Member)):
            embed.add_field(
                name=_("User") if not target.bot else _("Bot"), value=str(target)
            )
        elif isinstance(target, discord.TextChannel):
            embed.add_field(name=_("Channel"), value=target.mention)
        user = self.sonata.get_user(case.user_id) or await self.sonata.fetch_user(
            case.user_id
        )
        embed.add_field(name=_("Moderator"), value=str(user))
        if case.reason:
            embed.add_field(name=_("Reason"), value=case.reason, inline=False)
        embed.set_footer(text=f"ID: {case.id}")
        return embed

    async def create_modlog_case(
        self, ctx: core.Context, target, action, reason: str,
    ):
        created_at = datetime.utcnow()
        case = ModlogCase(
            created_at=created_at,
            guild_id=ctx.guild.id,
            id=discord.utils.time_snowflake(created_at),
            action=action.value,
            user_id=ctx.author.id,
            target_id=target.id,
            reason=reason,
        )
        self.sonata.dispatch("modlog_case", case)

    @core.group(usage="<id>", invoke_without_command=True)
    @commands.check(checks.is_mod())
    async def case(self, ctx: core.Context, case: ModlogCaseConverter()):
        embed = await self.make_case_embed(case)
        await ctx.send(embed=embed)

    @case.command(name="edit", usage="<id> <reason>")
    async def case_edit(
        self, ctx: core.Context, case: ModlogCaseConverter(), *, reason: clean_content()
    ):
        case.reason = reason
        await ctx.db.modlog_cases.update_one(
            {"guild_id": case.guild_id, "id": case.id},
            {"$set": {"reason": case.reason}},
        )
        await ctx.message.add_reaction("✅")
        channel = await self.get_modlog_channel(case.guild_id)
        if not channel:
            return
        embed = await self.make_case_embed(case)
        embed.description = _("Reason changed.")
        await channel.send(embed=embed)
