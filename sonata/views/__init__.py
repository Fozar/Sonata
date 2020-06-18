from .cogs import CogList, Cog
from .guilds import Guilds, Guild, GuildStats, GuildEmojis, GuildMembers
from .auth import Auth, AuthCallback, AuthLogout
from .users import UserMe


async def init_views(app):
    cors = app["cors"]
    cors.add(app.router.add_route("*", "/guilds", Guilds))
    cors.add(app.router.add_route("*", r"/guilds/{id}", Guild))
    cors.add(app.router.add_route("*", r"/guilds/{id}/stats", GuildStats))
    cors.add(app.router.add_route("*", r"/guilds/{id}/emojis", GuildEmojis))
    cors.add(app.router.add_route("*", r"/guilds/{id}/members", GuildMembers))
    cors.add(app.router.add_route("*", r"/users/@me", UserMe))
    cors.add(app.router.add_route("*", "/cogs", CogList))
    cors.add(app.router.add_route("*", r"/cogs/{name}", Cog))
    cors.add(app.router.add_route("*", "/auth", Auth))
    cors.add(app.router.add_route("*", "/auth/callback", AuthCallback))
    cors.add(app.router.add_route("*", "/auth/logout", AuthLogout))
