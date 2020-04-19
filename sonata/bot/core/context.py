import discord
from discord.ext import commands


class Context(commands.Context):
    @property
    def session(self):
        return self.bot.session

    @property
    def db(self):
        return self.bot.db

    async def send_help(self, *args):
        await super().send_help(self.command, *args)

    async def inform(self, description: str, **kwargs):
        colour = (
            self.command.cog.colour if self.command.cog else discord.Colour(0x9B9B9B)
        )
        embed = discord.Embed(colour=colour, description=description, **kwargs)
        return await self.send(embed=embed)
