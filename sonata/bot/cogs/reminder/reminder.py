import asyncio
from datetime import datetime, timedelta
from typing import Union, Any

import discord
import pytz
from babel.dates import format_datetime
from discord.ext import commands, menus

from sonata.bot import core, Sonata
from sonata.bot.utils.converters import UserFriendlyTime
from sonata.db.models import Reminder as ReminderModel


class ReminderListSource(menus.ListPageSource):
    def __init__(self, entries, colour: discord.Colour, locale: str, *, per_page):
        super().__init__(entries, per_page=per_page)
        self.colour = colour
        self.locale = locale

    async def format_page(self, menu: menus.MenuPages, entries: Any):
        embed = discord.Embed(title=_("Reminder list"), colour=self.colour)
        for reminder in entries:
            value = f"**ID**: {reminder['id']}\n**Remind**: {reminder['reminder']}"
            embed.add_field(
                name=format_datetime(
                    reminder["expires_at"], format="long", locale=self.locale
                ),
                value=value,
                inline=False,
            )
        return embed


class Reminder(
    core.Cog,
    colour=discord.Colour.teal(),
    description=_(
        "This module allows you to create reminders for a specific event after a "
        "certain amount of time using natural language."
    ),
):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata
        self._have_data = asyncio.Event(loop=sonata.loop)
        self._current_reminder = None
        self._task = sonata.loop.create_task(self.dispatch_reminders())

    def cog_unload(self):
        self._task.cancel()

    @commands.Cog.listener()
    async def on_reminder_complete(self, reminder: ReminderModel):
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

        embed = discord.Embed(colour=self.colour)

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

        embed.title = _("Reminder")
        embed.description = _("**Remind you**: {remind}\n**Date**: {date}").format(
            remind=reminder.reminder,
            date=format_datetime(
                reminder.expires_at, format="long", locale=self.sonata.locale
            ),
        )

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
            return ReminderModel(**reminder)
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

    async def call_reminder(self, reminder: ReminderModel):
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
        reminder = ReminderModel(
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

    @core.group(
        aliases=["reminder"],
        invoke_without_command=True,
        examples=[
            _("10/10/2024 go to the dentist"),
            _("after 2 years check if i won the argument"),
            _("after 30 minutes start stream on Twitch"),
        ],
    )
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
        
        The timedelta cannot be more than 5 years."""
        )
        if ctx.invoked_subcommand is not None:
            return
        desc = _("**Remind**: {remind}\n**Date**: {date}").format(
            remind=remind.arg,
            date=format_datetime(remind.dt, format="long", locale=self.sonata.locale),
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
            return await ctx.inform(_("No active reminders."))

        pages = menus.MenuPages(
            source=ReminderListSource(reminders, self.colour, ctx.locale, per_page=10),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    @remind.command(
        name="remove",
        aliases=["delete"],
        usage="<id>",
        ignore_extra=False,
        examples=["702553022131208657"],
    )
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
