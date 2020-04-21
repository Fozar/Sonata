from discord.ext import commands


def load_extension(bot: commands.Bot, cog_name: str):
    bot.load_extension(f"{__name__}.{cog_name}")


def unload_extension(bot: commands.Bot, cog_name: str):
    bot.unload_extension(f"{__name__}.{cog_name}")


def reload_extension(bot: commands.Bot, cog_name: str):
    bot.reload_extension(f"{__name__}.{cog_name}")
