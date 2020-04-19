from .stats import Stats


def setup(bot):
    bot.add_cog(Stats(bot))
