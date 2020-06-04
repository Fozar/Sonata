from .cogs import CogList, Cog
from .guild import Guild


async def init_views(app):
    cors = app["cors"]
    cors.add(app.router.add_route("*", "/guilds", Guild))
    cors.add(app.router.add_route("*", "/cogs", CogList))
    cors.add(app.router.add_route("*", r"/cogs/{name}", Cog))
