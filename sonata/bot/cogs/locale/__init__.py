from .locale import Locale


def setup(bot):
    bot.add_cog(Locale(bot))
