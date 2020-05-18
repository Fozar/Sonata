import discord
from discord.ext import menus


class CloseMenu(menus.Menu):
    def __init__(self, msg: str = None, embed: discord.Embed = None):
        super().__init__(timeout=30.0, clear_reactions_after=True)
        self.msg = msg
        self.embed = embed
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return await channel.send(self.msg, embed=self.embed)

    @menus.button("❌")
    async def do_close(self, payload):
        self.result = True
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class ConfirmMenu(menus.Menu):
    def __init__(self, msg: str = None, embed: discord.Embed = None):
        super().__init__(timeout=30.0, clear_reactions_after=True)
        self.msg = msg
        self.embed = embed
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return await channel.send(self.msg, embed=self.embed)

    @menus.button("✅")
    async def do_confirm(self, payload):
        self.result = True
        self.stop()

    @menus.button("❌")
    async def do_deny(self, payload):
        self.result = False
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result
