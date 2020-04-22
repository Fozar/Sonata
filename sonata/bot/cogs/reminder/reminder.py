import asyncio
from datetime import datetime, timedelta

import discord
import pytz
from babel.dates import format_datetime
from discord.ext import commands

from sonata.bot import core, Sonata
from sonata.bot.utils import i18n
from sonata.bot.utils.converters import UserFriendlyTime
from sonata.db import models


class Reminder(core.Cog, colour=discord.Colour(0x50E3C2)):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata
        self._have_data = asyncio.Event(loop=sonata.loop)
        self._current_timer = None
        self._task = sonata.loop.create_task(self.dispatch_reminders())

    @commands.Cog.listener()
    async def on_reminder_complete(self, reminder: models.Reminder):
        try:
            if "guild_id" in reminder:
                guild = self.sonata.get_guild(
                    reminder.guild_id
                ) or await self.sonata.fetch_guild(reminder.guild_id)
            else:
                guild = None
        except discord.HTTPException:
            return

        try:
            if guild is not None:
                channel = guild.get_channel(reminder.channel_id)
            else:
                channel: discord.TextChannel = self.sonata.get_channel(
                    reminder.channel_id
                ) or self.sonata.fetch_channel(reminder.channel_id)
            if channel is None:
                channel: discord.User = self.sonata.get_user(
                    reminder.user_id
                ) or self.sonata.fetch_user(reminder.user_id)
        except discord.HTTPException:
            return

        try:
            message = await channel.fetch_message(reminder.id)
        except discord.HTTPException:
            return

        await self.sonata.set_locale(message)

        desc = _("**Remind you**: {remind}\n**Date**: {date}").format(
            remind=reminder.reminder,
            date=format_datetime(
                reminder.expires_at, format="long", locale=i18n.current_locale.get()
            ),
        )
        embed = discord.Embed(
            title=_("Reminder"),
            description=desc,
            url=message.jump_url,
            colour=self.colour,
        )

        try:
            await channel.send(f"{message.author.mention}", embed=embed)
        except discord.HTTPException:
            return

    async def get_active_reminder(self, *, days=7):
        cursor = self.sonata.db.reminders.find(
            {
                "active": True,
                "expires_at": {"$lte": datetime.utcnow() + timedelta(days=days)},
            },
            sort=[("expires_at", 1)],
        )
        if await cursor.fetch_next:
            reminder = cursor.next_object()
            return models.Reminder(**reminder)
        else:
            return None

    async def wait_for_active_reminders(self, *, days=7):
        reminder = await self.get_active_reminder(days=days)
        if reminder is not None:
            self._have_data.set()
            return reminder

        self._have_data.clear()
        self._current_timer = None
        await self._have_data.wait()
        return await self.get_active_reminder(days=days)

    async def call_reminder(self, reminder: models.Reminder):
        await self.sonata.db.reminders.update_one(
            {"id": reminder.id}, {"$set": {"active": False}}
        )
        self.sonata.dispatch("reminder_complete", reminder)

    async def dispatch_reminders(self):
        try:
            while not self.sonata.is_closed():
                reminder = self._current_timer = await self.wait_for_active_reminders(
                    days=40
                )
                now = datetime.utcnow()
                if reminder.expires_at >= now:
                    to_sleep = (reminder.expires_at - now).total_seconds()
                    await asyncio.sleep(to_sleep)

                await self.call_reminder(reminder)
        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed):
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_reminders())

    async def short_reminder_optimisation(self, seconds, reminder):
        await asyncio.sleep(seconds)
        self.sonata.dispatch("reminder_complete", reminder)

    async def create_reminder(self, ctx: core.Context, remind):
        now = ctx.message.created_at.replace(tzinfo=pytz.utc)
        when = remind.dt.astimezone(pytz.utc)
        reminder = models.Reminder(
            id=ctx.message.id,
            created_at=now,
            reminder=remind.arg,
            expires_at=when,
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            channel_id=ctx.channel.id,
        )
        delta = (when - now).total_seconds()
        if delta <= 60:
            self.sonata.loop.create_task(
                self.short_reminder_optimisation(delta, reminder)
            )
            return reminder

        await ctx.db.reminders.insert_one(reminder.dict())
        if delta <= (86400 * 40):
            self._have_data.set()

        if self._current_timer and when < self._current_timer.expires:
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_reminders())

        return reminder

    @core.command()
    async def remind(
        self, ctx: core.Context, *, remind: UserFriendlyTime(commands.clean_content)
    ):
        desc = _("**Remind**: {remind}\n**Date**: {date}").format(
            remind=remind.arg,
            date=format_datetime(
                remind.dt, format="long", locale=i18n.current_locale.get()
            ),
        )
        msg, response = await ctx.confirm(
            desc, title=_("Create a reminder?"), timestamp=remind.dt
        )
        if not response:
            embed = discord.Embed(title=_("Reminder creation canceled"))
            await msg.edit(embed=embed)
            return

        await self.create_reminder(ctx, remind)
        embed = discord.Embed(
            title=_("Reminder created"), description=desc, timestamp=remind.dt, colour=self.colour
        )
        await msg.edit(embed=embed)
