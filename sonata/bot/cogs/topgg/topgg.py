import dbl

from sonata.bot import core


class TopGG(core.Cog):
    """Handles interactions with the top.gg API"""

    def __init__(self, sonata: core.Sonata, token):
        self.sonata = sonata
        self.token = token
        self.dblpy = dbl.DBLClient(self.sonata, self.token, autopost=True)

    async def on_guild_post(self):
        self.sonata.logger.debug("Server count posted successfully")
