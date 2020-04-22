from datetime import datetime
from typing import Union

import discord
from babel.dates import format_datetime
from dateparser import search
from discord.ext import commands

from sonata.bot import core, Sonata
from sonata.bot.utils import i18n
from sonata.bot.utils.misc import locale_to_language
from sonata.db import models


class Reminder(core.Cog):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata

    @core.command()
    async def remind(
        self, ctx: core.Context, *, remind: Union[commands.clean_content, str]
    ):
        languages = [
            locale_to_language(locale) for locale in i18n.gettext_translations.keys()
        ]
        date = search.search_dates(remind, languages=languages)
        if date is None:
            return await ctx.inform(_("Could not recognize the date."))

        date = date[0]

        if date[1] <= datetime.utcnow():
            return await ctx.inform(_("A reminder should be for the future."))

        remind = (remind.replace(date[0], "")).strip()
        desc = _("**Remind**: {remind}\n**Date**: {date}").format(
            remind=remind,
            date=format_datetime(
                date[1], format="long", locale=i18n.current_locale.get()
            ),
        )
        msg, response = await ctx.confirm(desc, title=_("Create a reminder?"))
        if not response:
            embed = discord.Embed(title=_("Reminder creation canceled"))
            await msg.edit(embed=embed)
            return

        reminder = models.Reminder(
            created_at=ctx.message.created_at,
            reminder=remind,
            expires_at=date[1],
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            channel_id=ctx.channel.id,
        ).dict()
        await ctx.db.reminders.insert_one(reminder)
        embed = discord.Embed(title=_("Reminder created"))
        await msg.edit(embed=embed)
