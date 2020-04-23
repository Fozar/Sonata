import asyncio
import contextlib
import functools
from typing import Iterable, Union, Optional

import discord

from sonata.bot import core


class Paginator:
    def __init__(
        self,
        pages: Optional[list] = None,
        controls: Optional[dict] = None,
        timeout: float = 30.0,
    ):
        self.pages = pages
        self.controls = controls
        self.timeout = timeout

    @property
    def controls(self):
        return self._controls

    @controls.setter
    def controls(self, _controls: dict):
        if _controls is None:
            self._controls = {
                "⬅": self.prev_page,
                "❌": self.close_pages,
                "➡": self.next_page,
            }
        else:
            for key, value in _controls.items():
                is_coroutine = value
                if isinstance(value, functools.partial):
                    is_coroutine = value.func
                if not asyncio.iscoroutinefunction(is_coroutine):
                    raise RuntimeError("Function must be a coroutine")
            self._controls = _controls

    def add_page(self, page: str):
        if not isinstance(page, str):
            raise RuntimeError("Page must be of `str` type")
        if self.__len__() > 0:
            self.pages.append(page)
        else:
            self.pages = [page]

    def add_pages(self, pages: list):
        for page in pages:
            self.add_page(page)

    def remove_page(self, page_index: int):
        del self.pages[page_index]

    def __len__(self) -> int:
        if self.pages is not None:
            return len(self.pages)
        else:
            return 0

    # noinspection DuplicatedCode
    async def send_pages(
        self, ctx: core.Context, message: discord.Message = None, page: int = 0,
    ):
        current_page = self.pages[page]
        if not message:
            message = await ctx.channel.send(content=current_page)
            await self.add_reactions(message, self.controls.keys())
        else:
            try:
                await message.edit(content=current_page)
            except discord.NotFound:
                return

        await self.wait_for_reaction(ctx, message, page)

    @staticmethod
    async def add_reactions(
        message: discord.Message, emojis: Iterable[Union[str, discord.Emoji]]
    ):
        with contextlib.suppress(discord.NotFound):
            for emoji in emojis:
                await message.add_reaction(emoji)

    async def wait_for_reaction(self, ctx, message, page):
        try:
            reaction, member = await ctx.bot.wait_for(
                "reaction_add",
                check=(
                    lambda _reaction, _member: _member == ctx.author
                    and _reaction.emoji in self.controls.keys()
                    and _reaction.message.id == message.id
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            try:
                await message.clear_reactions()
            except discord.Forbidden:  # cannot remove all reactions
                for key in self.controls.keys():
                    await message.remove_reaction(key, ctx.bot.user)
            except discord.NotFound:
                return
        else:
            return await self.controls[reaction.emoji](
                ctx, message, page, reaction.emoji
            )

    async def next_page(
        self, ctx, message: discord.Message, page: int, emoji: str,
    ):
        perms = message.channel.permissions_for(ctx.me)
        if perms.manage_messages:  # Can manage messages, so remove react
            with contextlib.suppress(discord.NotFound):
                await message.remove_reaction(emoji, ctx.author)
        if page == len(self.pages) - 1:
            page = 0  # Loop around to the first item
        else:
            page = page + 1
        return await self.send_pages(ctx, message, page)

    async def prev_page(
        self, ctx, message: discord.Message, page: int, emoji: str,
    ):
        perms = message.channel.permissions_for(ctx.me)
        if perms.manage_messages:  # Can manage messages, so remove react
            with contextlib.suppress(discord.NotFound):
                await message.remove_reaction(emoji, ctx.author)
        if page == 0:
            page = len(self.pages) - 1  # Loop around to the last item
        else:
            page = page - 1
        return await self.send_pages(ctx, message, page)

    # noinspection PyUnusedLocal
    @staticmethod
    async def close_pages(
        ctx, message: discord.Message, page: int, emoji: str,
    ):
        with contextlib.suppress(discord.NotFound):
            await message.delete()


class EmbedPaginator(Paginator):
    def add_page(self, page: discord.Embed):
        if not isinstance(page, discord.Embed):
            raise RuntimeError("Page must be of `discord.Embed` type")
        if self.__len__() > 0:
            self.pages.append(page)
        else:
            self.pages = [page]

    # noinspection DuplicatedCode
    async def send_pages(
        self, ctx, message: discord.Message = None, page: int = 0,
    ):
        current_page = self.pages[page]
        if not message:
            message = await ctx.channel.send(embed=current_page)
            await self.add_reactions(message, self.controls.keys())
        else:
            try:
                await message.edit(embed=current_page)
            except discord.NotFound:
                return

        await self.wait_for_reaction(ctx, message, page)
