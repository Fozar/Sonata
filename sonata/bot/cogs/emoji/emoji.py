import re
from collections import Counter
from datetime import datetime
from typing import Union, Sequence

import discord
import emoji as _emoji
from dateutil.parser import parse
from discord.ext import commands

from sonata.bot import core
from sonata.db.models import EmojiStats

EMOJI_REGEX = re.compile(r"<a?:.+?:([0-9]{15,21})>")


class Emoji(
    core.Cog,
    colour=discord.Color.gold(),
    description=_(
        "The module allows you to get detailed information about emoji, and also keeps "
        "emoji usage statistics."
    ),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self.recalc_started_at = None

    @core.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not await self.sonata.should_reply(message) or not message.guild:
            return

        if (
            self.recalc_started_at is not None
            and self.recalc_started_at <= message.created_at
        ):
            return

        matches = set(EMOJI_REGEX.findall(message.content))
        if not matches:
            return

        for emoji_id, amount in dict(Counter(map(int, matches))).items():
            if self.sonata.emoji(emoji_id) is None:
                return

            result = await self.sonata.db.emoji_stats.update_one(
                {"guild_id": message.guild.id, "id": emoji_id},
                {"$inc": {"total": amount}},
            )
            if result.matched_count == 0:
                await self.insert_emoji_stats(
                    emoji_id, message.guild.id, message.created_at
                )

    @core.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: Sequence[discord.Emoji],
        after: Sequence[discord.Emoji],
    ):
        def diff(li1, li2):
            return list(set(li1) - set(li2))

        deleted = diff(before, after)
        new = diff(after, before)
        for emoji in deleted:
            self.sonata.db.emoji_stats.delete_one(
                {"guild_id": guild.id, "id": emoji.id}
            )
        for emoji in new:
            await self.insert_emoji_stats(
                emoji.id, guild.id, discord.utils.snowflake_time(emoji.id)
            )

    async def insert_emoji_stats(
        self, emoji_id: int, guild_id: int, created_at: datetime
    ):
        emoji_stats = EmojiStats(
            id=emoji_id, guild_id=guild_id, total=1, created_at=created_at,
        ).dict()
        await self.sonata.db.emoji_stats.insert_one(emoji_stats)

    @core.group(
        invoke_without_command=True, examples=["😃"]
    )
    async def emoji(
        self, ctx: core.Context, emoji: Union[discord.Emoji, discord.PartialEmoji, str]
    ):
        _("""Shows emoji info""")
        if ctx.invoked_subcommand is not None:
            return
        embed = discord.Embed(colour=self.colour)
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

    @emoji.command(name="stats", ignore_extra=False)
    @commands.guild_only()
    async def emoji_stats(self, ctx: core.Context):
        _("""Emoji statistics""")
        cursor = ctx.db.emoji_stats.find(
            {"guild_id": ctx.guild.id},
            {"id": True, "total": True},
            sort=[("total", -1)],
            limit=24,
        )
        embed = discord.Embed(colour=self.colour, title=_("Emoji statistics"))
        total = 0
        while await cursor.fetch_next:
            emoji = cursor.next_object()
            emoji_total = emoji["total"]
            total += emoji_total
            embed.add_field(
                name=str(ctx.bot.emoji(emoji["id"])), value=str(emoji_total)
            )
        if len(embed.fields) == 0:
            embed.description = _("Empty")
        else:
            embed.description = _("**Total**: {0}").format(total)
        await ctx.send(embed=embed)

    @core.command(name="recalc.emoji", hidden=True)
    @commands.is_owner()
    async def recalculate_emoji(self, ctx: core.Context, *, date: str):
        status = await ctx.send("```Initialization...```")
        self.recalc_started_at = ctx.message.created_at
        date = parse(date)
        now = datetime.utcnow()
        await ctx.db.emoji_stats.delete_many({})
        await status.edit(content="```Emoji stats reset```")

        for guild in self.sonata.guilds:
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
                    await status.edit(content=f"```{guild.name}: recalc - {dt}```")
                await self.on_message(message)
        self.recalc_started_at = None
        await status.edit(content="```Done```")
