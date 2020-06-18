import asyncio
from datetime import datetime, timedelta
from typing import Union, Optional

import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core
from sonata.bot.utils.converters import ModlogCaseConverter
from sonata.db.models import ModlogCase

action_mapping = {
    discord.AuditLogAction.kick: _("Member kicked"),
    discord.AuditLogAction.ban: _("User banned"),
    discord.AuditLogAction.unban: _("User unbanned"),
    discord.AuditLogAction.message_bulk_delete: _("Messages purged"),
    discord.AuditLogAction.overwrite_create: _("Member muted"),
    discord.AuditLogAction.overwrite_delete: _("Member unmuted"),
}


async def modlog_enabled(ctx: core.Context):
    guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"modlog": True})
    return guild.get("modlog", False)


class Modlog(core.Cog):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self._have_data = asyncio.Event(loop=sonata.loop)
        self._next_case = None
        self._task = sonata.loop.create_task(self.dispatch_cases())

    def cog_unload(self):
        self._task.cancel()

    @core.Cog.listener()
    async def on_modlog_case_create(self, case: ModlogCase):
        channel = await self.get_modlog_channel(case.guild_id)
        if not channel:
            return

        await self.sonata.db.modlog_cases.insert_one(case.dict())
        self.sonata.locale = await self.sonata.define_locale(channel)
        embed = await self.make_case_embed(case)
        try:
            await channel.send(embed=embed)
            return
        except discord.Forbidden:
            await self.sonata.db.guilds.update_one(
                {"id": case.guild_id}, {"$set": {"modlog": None}}
            )

    @core.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User]
    ):
        case = await self.fetch_modlog_case(guild, user, discord.AuditLogAction.ban)
        if case:
            self.sonata.dispatch("modlog_case_create", case)

    @core.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        case = await self.fetch_modlog_case(
            member.guild, member, discord.AuditLogAction.kick
        )
        if case:
            self.sonata.dispatch("modlog_case_create", case)

    @core.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        action = discord.AuditLogAction.unban
        await self.sonata.db.modlog_cases.update_many(
            {
                "guild_id": guild.id,
                "target_id": user.id,
                "action": action.value,
                "expired": False,
            },
            {"$set": {"expired": True}},
        )
        case = await self.fetch_modlog_case(guild, user, action)
        if case:
            self.sonata.dispatch("modlog_case_create", case)

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
            await self.sonata.db.guilds.update_one(
                {"id": guild_id}, {"$set": {"modlog": None}}
            )
            return None
        else:
            return channel

    async def fetch_modlog_case(
        self, guild: discord.Guild, user: Union[discord.Member, discord.User], action
    ):
        try:
            me = guild.me or await guild.fetch_member(self.sonata.user.id)
        except discord.HTTPException:
            return
        if not me.guild_permissions.view_audit_log:
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
        target,
        action,
        reason: Optional[str],
        expires_at: datetime = None,
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
        self.sonata.dispatch("modlog_case_create", case)
        if expires_at:
            case.expires_at = expires_at
            case.expired = False
            delta = (case.expires_at - case.created_at).total_seconds()
            if delta <= 60:
                self.sonata.loop.create_task(self.short_case_optimisation(delta, case))
                return

            if delta <= (86400 * 40):
                self._have_data.set()

            if self._next_case and case.expires_at < self._next_case.expires_at:
                self._task.cancel()
                self._task = self.sonata.loop.create_task(self.dispatch_cases())

    async def get_active_case(self, *, days=7):
        cursor = self.sonata.db.modlog_cases.find(
            {
                "expired": False,
                "expires_at": {"$lte": datetime.utcnow() + timedelta(days=days)},
            },
            sort=[("expires_at", 1)],
        )
        if await cursor.fetch_next:
            case = cursor.next_object()
            return ModlogCase(**case)
        else:
            return None

    async def wait_for_active_cases(self, *, days=7):
        case = await self.get_active_case(days=days)
        if case is not None:
            self._have_data.set()
            return case

        self._have_data.clear()
        self._next_case = None
        await self._have_data.wait()
        return await self.get_active_case(days=days)

    async def call_case(self, case: ModlogCase):
        await self.sonata.db.modlog_cases.update_one(
            {"id": case.id}, {"$set": {"expired": True}}
        )
        self.sonata.dispatch("modlog_case_expire", case)

    async def dispatch_cases(self):
        try:
            while not self.sonata.is_closed():
                case = self._next_case = await self.wait_for_active_cases(days=40)
                now = datetime.utcnow()
                if case.expires_at >= now:
                    to_sleep = (case.expires_at - now).total_seconds()
                    await asyncio.sleep(to_sleep)

                await self.call_case(case)
        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed):
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_cases())

    async def short_case_optimisation(self, seconds, case):
        await asyncio.sleep(seconds)
        case.expired = True
        await self.sonata.db.modlog_cases.update_one(
            {"id": case.id}, {"$set": {"expired": True}}
        )
        self.sonata.dispatch("modlog_case_expire", case)

    @core.group(
        usage="<id>", invoke_without_command=True, examples=["717068675059810376"]
    )
    @core.mod_only()
    @commands.check(modlog_enabled)
    async def case(self, ctx: core.Context, case: ModlogCaseConverter()):
        _("""Returns modlog case by specified ID""")
        embed = await self.make_case_embed(case)
        await ctx.send(embed=embed)

    @case.command(
        name="edit", usage="<id> <reason>", examples=[_("717068675059810376 flood")]
    )
    @core.mod_only()
    @commands.check(modlog_enabled)
    async def case_edit(
        self, ctx: core.Context, case: ModlogCaseConverter(), *, reason: clean_content()
    ):
        _("""Edits modlog case reason by specified ID""")
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
