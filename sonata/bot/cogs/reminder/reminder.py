import asyncio
from datetime import datetime, timedelta
from typing import Union

import discord
import pytz
from babel.dates import format_datetime
from discord.ext import commands

from sonata.bot import core, Sonata
from sonata.bot.utils import i18n
from sonata.bot.utils.converters import UserFriendlyTime
from sonata.bot.utils.misc import chunks
from sonata.bot.utils.paginator import EmbedPaginator
from sonata.db import models


class Reminder(core.Cog, colour=discord.Colour(0x50E3C2)):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata
        self._have_data = asyncio.Event(loop=sonata.loop)
        self._current_reminder = None
        self._task = sonata.loop.create_task(self.dispatch_reminders())

    @commands.Cog.listener()
    async def on_reminder_complete(self, reminder: models.Reminder):
        try:
            channel: Union[
                discord.TextChannel, discord.DMChannel
            ] = self.sonata.get_channel(
                reminder.channel_id
            ) or self.sonata.fetch_channel(
                reminder.channel_id
            )
        except discord.HTTPException:
            return

        desc = _("**Remind you**: {remind}\n**Date**: {date}").format(
            remind=reminder.reminder,
            date=format_datetime(
                reminder.expires_at, format="long", locale=i18n.current_locale.get()
            ),
        )
        embed = discord.Embed(
            title=_("Reminder"), description=desc, colour=self.colour,
        )

        try:
            message = await channel.fetch_message(reminder.id)
        except discord.HTTPException:
            if isinstance(channel, discord.DMChannel):
                user = channel.recipient
            else:
                try:
                    user = self.sonata.get_user(
                        reminder.user_id
                    ) or await self.sonata.fetch_user(reminder.user_id)
                except discord.HTTPException:
                    return
                else:
                    await self.sonata.set_locale(channel.last_message)
        else:
            await self.sonata.set_locale(message)
            embed.url = message.jump_url
            user = message.author

        try:
            await channel.send(f"{user.mention}", embed=embed)
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
        self._current_reminder = None
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
                reminder = (
                    self._current_reminder
                ) = await self.wait_for_active_reminders(days=40)
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

        if self._current_reminder and when < self._current_reminder.expires_at.replace(
            tzinfo=pytz.utc
        ):
            self._task.cancel()
            self._task = self.sonata.loop.create_task(self.dispatch_reminders())

        return reminder

    @core.group(aliases=["reminder"], invoke_without_command=True)
    async def remind(
        self,
        ctx: core.Context,
        *,
        remind: UserFriendlyTime(commands.clean_content, "..."),
    ):
        _(
            """Reminds of something after a certain amount of time
        
        The input may be a date in your usual format or a time difference.
        It is recommended to check if I recognized the time correctly. \
        In the Date field, you will see the date in UTC. Even lower will \
        be the date in your local time.
        
        Examples:
        
        - 10/10/2024 go to the dentist
        - after 2 years check if i won the argument
        - after 30 minutes start stream on Twitch
        
        The timedelta cannot be more than 5 years."""
        )
        if ctx.invoked_subcommand is not None:
            return
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
            embed = discord.Embed(
                title=_("Reminder creation canceled"), colour=self.colour
            )
            await msg.edit(embed=embed)
            return

        reminder = await self.create_reminder(ctx, remind)
        embed = discord.Embed(
            title=_("Reminder created"),
            description=desc,
            timestamp=remind.dt,
            colour=self.colour,
        )
        embed.set_footer(text=f"ID: {reminder.id}")
        await msg.edit(embed=embed)

    @remind.command(name="list", ignore_extra=False)
    async def remind_list(self, ctx: core.Context):
        _("""Makes a list of active reminders.""")
        cursor = self.sonata.db.reminders.find(
            {"active": True, "user_id": ctx.author.id},
            {"id": True, "channel_id": True, "reminder": True, "expires_at": True},
        ).sort([("expires_at", 1)])
        reminders = await cursor.to_list(length=None)
        if not reminders:
            await ctx.inform(_("No active reminders."))
        current_locale = i18n.current_locale.get()
        pages = []
        for reminders in chunks(reminders, 10):
            embed = discord.Embed(title=_("Reminder list"), colour=self.colour)
            for reminder in reminders:
                _id = reminder["id"]
                try:
                    channel = self.sonata.get_channel(
                        reminder["channel_id"]
                    ) or await self.sonata.fetch_channel(reminder["channel_id"])
                    message = await channel.fetch_message(reminder["id"])
                except discord.HTTPException:
                    pass
                else:
                    _id = f"[{_id}]({message.jump_url})"
                value = f"**ID**: {_id}\n**Remind**: {reminder['reminder']}"
                embed.add_field(
                    name=format_datetime(
                        reminder["expires_at"], format="long", locale=current_locale
                    ),
                    value=value,
                    inline=False,
                )
            pages.append(embed)
        if len(pages) > 1:
            paginator = EmbedPaginator()
            paginator.add_pages(pages)
            return await paginator.send_pages(ctx)

        await ctx.send(embed=pages[0])

    @remind.command(name="remove", aliases=["delete"], usage="<id>", ignore_extra=False)
    async def remind_remove(self, ctx: core.Context, _id: int):
        _("""Deletes a reminder by ID""")
        result = await ctx.db.reminders.update_one(
            {"user_id": ctx.author.id, "id": _id}, {"$set": {"active": False}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("Reminder not found."))
        else:
            await ctx.inform(_("Reminder deleted."))

    @remind.command(name="clear", ignore_extra=False)
    async def remind_clear(self, ctx: core.Context):
        _("""Deletes all reminders""")
        result = await ctx.db.reminders.update_many(
            {"user_id": ctx.author.id}, {"$set": {"active": False}}
        )
        if result.modified_count == 0:
            await ctx.inform(_("You have no active reminders."))
        else:
            await ctx.inform(_("Reminders deleted."))
