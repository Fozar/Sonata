import asyncio

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

    async def confirm(self, description: str, timeout: float = 30.0, **kwargs):
        msg = await self.inform(description, **kwargs)
        reactions = ("✅", "❌")
        for reaction in reactions:
            await msg.add_reaction(reaction)

        def check(reaction, user):
            return user == self.author and str(reaction.emoji) in reactions

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", timeout=timeout, check=check
            )
        except asyncio.TimeoutError:
            response = False
        else:
            response = True if str(reaction.emoji) == reactions[0] else False
        for reaction in reactions:
            await msg.remove_reaction(
                reaction, self.guild.me if self.guild else self.bot.user
            )
        return msg, response
