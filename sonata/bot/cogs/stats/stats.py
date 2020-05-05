from datetime import datetime
from typing import Optional

import discord
from dateutil.parser import parse
from discord import abc
from discord.ext import commands

from sonata.bot import core
from sonata.bot.cogs.stats.leveling import Leveling
from sonata.db.models import Guild, User, Command, DailyStats, UserStats


class Stats(
    Leveling, description=_("""Sonata statistics"""), colour=discord.Colour(0xF5A623)
):
    def __init__(self, sonata: core.Sonata):
        super().__init__(sonata)
        self.recalc_started_at = None
        self.service_guild: Optional[discord.Guild] = None
        self.errors_channel: Optional[discord.TextChannel] = None

    @core.Cog.listener()
    async def on_ready(self):
        self.service_guild = self.sonata.get_guild(313726240710197250)
        self.errors_channel = self.service_guild.get_channel(707180649454370827)
        for command in self.sonata.walk_commands():
            guild_conf = self.sonata.db.commands.find(
                {"name": command.qualified_name}, {"name": True}
            ).limit(1)
            if await guild_conf.fetch_next:
                continue

            command_conf = Command(
                name=command.qualified_name,
                cog=command.cog.qualified_name if command.cog else None,
                enabled=command.enabled,
            ).dict()
            await self.sonata.db.commands.insert_one(command_conf)
        for guild in self.sonata.guilds:
            await self.on_guild_join(guild)

    @core.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.sonata.should_reply(message):
            return

        if (
            self.recalc_started_at is not None
            and self.recalc_started_at <= message.created_at
        ):
            return

        if message.guild:
            await self.update_guild_stats(message)
        await self.update_user_stats(message)

    @core.Cog.listener()
    async def on_command(self, ctx: core.Context):
        await ctx.db.commands.update_one(
            {"name": ctx.command.qualified_name}, {"$inc": {"invocation_counter": 1}}
        )
        await ctx.db.user_stats.update_one(
            {"guild_id": ctx.guild.id, "user_id": ctx.author.id},
            {"$inc": {"commands_invoked": 1}},
        )
        if ctx.guild:
            date = ctx.message.created_at.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            await ctx.db.daily_stats.update_one(
                {"date": date, "guild_id": ctx.guild.id},
                {"$inc": {"commands_invoked": 1}},
            )

    @core.Cog.listener()
    async def on_command_error(self, ctx: core.Context, exception: Exception):
        if ctx.command:
            await ctx.db.commands.update_one(
                {"name": ctx.command.qualified_name}, {"$inc": {"error_count": 1}}
            )

            embed = discord.Embed(
                colour=self.colour,
                title=f"Ошибка в команде {ctx.command.qualified_name}",
                timestamp=ctx.message.created_at,
            )
            embed.description = (
                f"{ctx.message.content}\n\n" f"**- {exception}**```py\n{exception.args}```"
            )
            while hasattr(exception, "original"):
                exception = exception.original
                if hasattr(exception, "args"):
                    embed.description += f"**- {exception}**```py\n{exception.args}```"
            embed.add_field(name="Гильдия", value=ctx.guild.name)
            embed.add_field(name="Автор", value=str(ctx.author))
            embed.add_field(name="Канал", value=ctx.channel.name)
            await self.errors_channel.send(embed=embed)

    @core.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_conf = await self.sonata.db.guilds.find_one_and_update(
            {"id": guild.id}, {"$set": {"name": guild.name, "left": None}}
        )
        if not guild_conf:
            guild_conf = Guild(id=guild.id, name=guild.name)
            await self.sonata.db.guilds.insert_one(guild_conf.dict())
        for member in guild.members:
            await self.on_member_join(member)

    @core.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self.sonata.db.guilds.update_one(
            {"id": guild.id}, {"$currentDate": {"left": True}}
        )

    @core.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            await self.sonata.db.guilds.update_one(
                {"id": before.id}, {"$set": {"name": after.name}}
            )

    @core.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        result = await self.sonata.db.users.update_one(
            {"id": member.id},
            {"$set": {"name": str(member)}, "$addToSet": {"guilds": member.guild.id}},
        )
        if result.matched_count == 0:
            member_conf = User(id=member.id, name=str(member)).dict()
            await self.sonata.db.users.insert_one(member_conf)

    @core.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await self.sonata.db.users.update_one(
            {"id": member.id}, {"$pull": {"guilds": member.guild.id}}
        )

    @core.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if str(before) != str(after):
            await self.sonata.db.users.update_one(
                {"id": before.id}, {"$set": {"name": str(after)}}
            )

    @core.Cog.listener()
    async def on_private_channel_create(self, channel: abc.PrivateChannel):
        if isinstance(channel, discord.DMChannel):
            user = channel.recipient
            user_conf = self.sonata.db.users.find({"id": user.id}, {"id": True}).limit(
                1
            )
            if not await user_conf.fetch_next:
                user_conf = User(id=user.id, name=str(user)).dict()
                await self.sonata.db.users.insert_one(user_conf)

    async def lvl_up(self, message, exp, lvl):
        if self.recalc_started_at is not None:
            return
        await super().lvl_up(message, exp, lvl)

    async def update_user_stats(self, message: discord.Message):
        stats = await self.sonata.db.user_stats.find_one_and_update(
            {"guild_id": message.guild.id, "user_id": message.author.id},
            {"$inc": {"total_messages": 1}},
            {"_id": False, "last_exp_at": True, "exp": True, "lvl": True},
        )
        if not stats:
            stats = UserStats(
                guild_id=message.guild.id, user_id=message.author.id, total_messages=1
            ).dict()
            await self.sonata.db.user_stats.insert_one(stats)
        if (
            stats.get("last_exp_at") is None
            or (message.created_at - stats["last_exp_at"]).total_seconds() >= 60
        ):
            await self.update_user_exp(message, stats["exp"], stats["lvl"])

    async def update_daily_stats(self, dt: datetime, guild: discord.Guild):
        date = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.sonata.db.daily_stats.update_one(
            {"date": date, "guild_id": guild.id}, {"$inc": {"total_messages": 1}}
        )
        if result.matched_count == 0:
            daily_stats = DailyStats(
                date=date, guild_id=guild.id, total_messages=1,
            ).dict()
            await self.sonata.db.daily_stats.insert_one(daily_stats)

    async def update_guild_stats(self, message: discord.Message):
        result = await self.sonata.db.guilds.update_one(
            {"id": message.guild.id}, {"$set": {"last_message_at": message.created_at}}
        )
        if result.matched_count != 0:
            await self.update_daily_stats(message.created_at, message.guild)

    @core.command(name="recalc.stats")
    @commands.is_owner()
    async def recalculate_stats(self, ctx: core.Context, *, date: str):
        self.recalc_started_at = ctx.message.created_at
        status = await ctx.send("```Initialization...```")
        date = parse(date)
        now = datetime.utcnow()
        await ctx.db.commands.update_many(
            {}, {"$set": {"invocation_counter": 0, "error_count": 0}}
        )
        await status.edit(content="```Commands reset```")
        await ctx.db.daily_stats.delete_many({})
        await status.edit(content="```Daily stats reset```")
        await ctx.db.user_stats.update_many(
            {},
            {
                "$set": {
                    "total_messages": 0,
                    "commands_invoked": 0,
                    "last_exp_at": None,
                    "created_at": date,
                    "lvl": 0,
                    "exp": 0,
                }
            },
        )
        await status.edit(content="```Users reset```")
        for guild in self.sonata.guilds:
            await ctx.db.guilds.update_one(
                {"id": guild.id},
                {"$set": {"last_message_at": None, "created_at": date}},
            )
            await status.edit(content=f"```Guild {guild.name} reset```")
            messages = []
            for channel in guild.channels:
                if not isinstance(channel, discord.TextChannel):
                    continue
                await status.edit(content=f"```Fetch: {guild.name} - {channel.name}```")
                messages += (
                    await channel.history(limit=None, after=date, before=now)
                    .filter(lambda msg: not msg.author.bot)
                    .flatten()
                )

            messages = sorted(messages, key=lambda msg: msg.created_at)
            dt = None
            for message in messages:
                if message.created_at.date() != dt:
                    dt = message.created_at.date()
                    await status.edit(content=f"```Recalc: {dt}```")
                await self.on_message(message)
                ctx = await self.sonata.get_context(message, cls=core.Context)
                if ctx.command:
                    await self.on_command(ctx)
        self.recalc_started_at = None
        await status.edit(content="```Done```")
