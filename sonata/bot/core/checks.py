import discord
from discord.ext import commands

from .context import Context
from .errors import NoPremium


def premium_only():
    """A :func:`.check` that indicates this command must only be used in a premium guild
    context only. Basically, no private messages are allowed when using the command.

    This check raises a special exception, :exc:`.NoPremium` that is inherited from
    :exc:`.CheckFailure`.
    """

    async def predicate(ctx: Context):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"premium": True})
        if not guild["premium"]:
            raise NoPremium()
        return True

    return commands.check(predicate)


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