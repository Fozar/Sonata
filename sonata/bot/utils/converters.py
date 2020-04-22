from datetime import timedelta

import pytz
from babel.dates import format_timedelta
from dateparser import search
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils import i18n
from sonata.bot.utils.misc import locale_to_language


class GlobalChannel(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            # Not found... so fall back to ID + global lookup
            try:
                channel_id = int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(
                    _("Could not find a channel by ID {0}.").format(repr(argument))
                )
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(
                        _("Could not find a channel by ID {0}.").format(repr(argument))
                    )
                return channel


class UserFriendlyTime(commands.Converter):
    def __init__(
        self,
        converter=None,
        future: bool = True,
        past: bool = False,
        max_delta: int = 86400 * 365 * 5,
    ):
        if isinstance(converter, type) and issubclass(converter, commands.Converter):
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):
            raise TypeError("commands.Converter subclass necessary.")

        self.converter = converter
        self.future = future
        self.past = past
        self.max_delta = timedelta(seconds=max_delta)
        self.arg = None
        self.dt = None

    async def convert(self, ctx: core.Context, argument):
        me = _("me")  # Like as "Remind me..."
        if argument.startswith(me):
            argument = argument[len(me) :].strip()
        languages = [
            locale_to_language(locale) for locale in i18n.gettext_translations.keys()
        ]
        date = search.search_dates(argument, languages=languages)
        if date is None:
            raise commands.BadArgument(_("Could not recognize the date."))

        try:
            now = ctx.message.created_at.replace(tzinfo=pytz.utc)
            date = date[0]
            when = date[1].astimezone(pytz.utc)
        except OSError:
            raise commands.BadArgument(_("An error occurred converting the date."))
        if not self.past and when <= now:
            raise commands.BadArgument(_("This time is in the past."))
        if not self.future and when > now:
            raise commands.BadArgument(_("This time is in the future."))
        if when - now > self.max_delta:
            raise commands.BadArgument(
                _("Maximum timedelta: {0}").format(
                    format_timedelta(self.max_delta, locale=i18n.current_locale.get())
                )
            )
        self.dt = when

        remaining = (argument.replace(date[0], "")).strip()
        if not remaining:
            raise commands.BadArgument(_("Missing argument before or after the time."))

        if self.converter is not None:
            self.arg = await self.converter.convert(ctx, remaining)
        else:
            self.arg = remaining

        return self
