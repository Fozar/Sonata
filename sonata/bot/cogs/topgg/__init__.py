from .topgg import TopGG
from ... import Sonata


def setup(bot: Sonata):
    topgg_token = bot.config["bot"].topgg_token
    if topgg_token:
        bot.add_cog(TopGG(bot, topgg_token))
