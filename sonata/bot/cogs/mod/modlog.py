import asyncio
from datetime import datetime, timedelta
from typing import Union

import discord

from sonata.bot import core
from sonata.db.models import ModlogCase


class Modlog(core.Cog):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.Cog.listener()
    async def on_modlog_case(self, case: ModlogCase):
        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": case.guild_id}, {"modlog": True}
        )
        if not guild_conf or not guild_conf.get("modlog"):
            return
        channel = self.sonata.get_channel(
            guild_conf["modlog"]
        ) or await self.sonata.fetch_channel(guild_conf["modlog"])
        await self.sonata.db.modlog_cases.insert_one(case.dict())
        embed = await self.make_case_embed(case)
        await channel.send(embed=embed)

    @core.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User]
    ):
        case = await self.fetch_modlog_case(guild, user, discord.AuditLogAction.ban)
        self.sonata.dispatch("modlog_case", case)

    @core.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        case = await self.fetch_modlog_case(
            member.guild, member, discord.AuditLogAction.kick
        )
        self.sonata.dispatch("modlog_case", case)

    @core.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        case = await self.fetch_modlog_case(guild, user, discord.AuditLogAction.unban)
        self.sonata.dispatch("modlog_case", case)

    async def fetch_modlog_case(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User], action
    ):
        if not guild.me.guild_permissions.view_audit_log:
            return

        guild_conf = await self.sonata.db.guilds.find_one(
            {"id": guild.id}, {"modlog": True}
        )
        if not guild_conf or not guild_conf.get("modlog", False):
            return
        now = datetime.utcnow()
        before = now + timedelta(minutes=1)
        after = now - timedelta(minutes=1)
        await asyncio.sleep(10)
        entry = await guild.audit_logs(action=action, before=before, after=after).find(
            lambda e: e.target.id == user.id and after < e.created_at < before
        )
        if not entry or entry.user.id == guild.me.id:
            return

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
        self,
        ctx: core.Context,
        target: Union[discord.Member, discord.User],
        action,
        reason: str,
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
