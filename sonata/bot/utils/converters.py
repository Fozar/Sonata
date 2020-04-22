from typing import Optional

import dateparser
from datetime import datetime
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
                    f"Could not find a channel by ID {argument!r}."
                )
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(
                        f"Could not find a channel by ID {argument!r}."
                    )
                return channel


class UserFriendlyTime(commands.Converter):
    async def convert(self, ctx: core.Context, argument) -> Optional[datetime]:
        languages = [
            locale_to_language(locale) for locale in i18n.gettext_translations.keys()
        ]
        _datetime = dateparser.parse(argument, languages=languages)
        if _datetime is None:
            raise commands.BadArgument(
                f"Failed to convert user date input: {argument!r}"
            )
        return _datetime
