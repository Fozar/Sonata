from .cogs import CogList, Cog
from .guild import Guild
from .auth import Auth, AuthCallback


async def init_views(app):
    cors = app["cors"]
    cors.add(app.router.add_route("*", "/guilds", Guild))
    cors.add(app.router.add_route("*", "/cogs", CogList))
    cors.add(app.router.add_route("*", r"/cogs/{name}", Cog))
    cors.add(app.router.add_route("*", "/auth", Auth))
    cors.add(app.router.add_route("*", "/auth/callback", AuthCallback))
