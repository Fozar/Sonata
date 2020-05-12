import discord
from discord.ext import commands

from sonata.bot.utils import i18n
from sonata.bot.utils.paginator import ConfirmMenu


class Context(commands.Context):
    @property
    def db(self):
        return self.bot.db

    @property
    def locale(self):
        return i18n.current_locale.get()

    @locale.setter
    def locale(self, value):
        i18n.current_locale.set(value)

    @property
    def pool(self):
        return self.bot.pool

    @property
    def session(self):
        return self.bot.session

    async def send_help(self, *args):
        await super().send_help(self.command, *args)

    @property
    def colour(self):
        return (
            self.command.cog.colour
            if self.command and self.command.cog
            else discord.Colour(0x9B9B9B)
        )

    async def inform(self, description: str, **kwargs):
        embed = discord.Embed(colour=self.colour, description=description, **kwargs)
        return await self.send(embed=embed)

    async def confirm(self, description: str, **kwargs):
        embed = discord.Embed(colour=self.colour, description=description, **kwargs)
        menu = ConfirmMenu(embed=embed)
        response = await menu.prompt(self)
        return menu.message, response
