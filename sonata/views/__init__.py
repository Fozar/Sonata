from .cog import Cog
from .command import Command
from .guild import Guild


async def init_views(app):
    cors = app["cors"]
    cors.add(app.router.add_route("*", "/guilds", Guild))
    cors.add(app.router.add_route("*", "/command", Command))
    cors.add(app.router.add_route("*", "/cog", Cog))
