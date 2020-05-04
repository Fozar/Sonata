import discord
from discord.ext import commands

from .context import Context


def is_mod():
    async def predicate(ctx: Context):
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"mod_roles": True})
        if (
            guild
            and guild.get("admin_roles")
            and discord.utils.find(
                lambda role: role.id in guild["mod_roles"], ctx.author.roles
            )
            is not None
        ):
            return True
        return False

    return commands.check(predicate)
