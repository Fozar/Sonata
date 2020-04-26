import re
from typing import Union

import discord
import emoji as _emoji
from discord.ext import commands

from sonata.bot import core

EMOJI_REGEX = re.compile(r"<a?:.+?:([0-9]{15,21})>")


class Emoji(core.Cog, colour=discord.Color(0xF5A623)):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.command()
    async def emoji(
        self, ctx: core.Context, emoji: Union[discord.Emoji, discord.PartialEmoji, str]
    ):
        _("""Shows emoji info""")
        embed = discord.Embed(colour=self.colour,)
        title = _('Emoji "{0}"')
        if isinstance(emoji, str):
            if (
                emoji not in _emoji.UNICODE_EMOJI
                and emoji not in _emoji.UNICODE_EMOJI_ALIAS
            ):
                raise commands.BadArgument(_("Invalid emoji."))
            embed.title = title.format(emoji)
            cldr_name = _emoji.demojize(emoji)
            embed.description = (
                cldr_name.replace(":", "").replace("_", " ").capitalize()
            )
            unicode = _emoji.EMOJI_UNICODE[cldr_name]
            embed.add_field(
                name=f"Unicode",
                value="`{0}`".format(
                    unicode.encode("raw_unicode_escape").decode("utf-8")
                ),
            )
        else:
            embed.title = title.format(emoji.name)
            embed.url = str(emoji.url)
            embed.set_image(url=str(emoji.url))
            embed.set_footer(text=f"ID: {emoji.id}")
        await ctx.send(embed=embed)
