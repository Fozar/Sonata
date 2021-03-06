from .cogs import CogList, Cog
from .commands import CommandSearch
from .guilds import Guilds, Guild, GuildStats, GuildEmojis, GuildMembers, GuildChannels, GuildRoles
from .auth import Auth, AuthCallback, AuthLogout
from .locales import Locales
from .users import UserMe


async def init_views(app):
    cors = app["cors"]
    cors.add(app.router.add_route("*", "/guilds", Guilds))
    cors.add(app.router.add_route("*", r"/guilds/{id}", Guild))
    cors.add(app.router.add_route("*", r"/guilds/{id}/stats", GuildStats))
    cors.add(app.router.add_route("*", r"/guilds/{id}/emojis", GuildEmojis))
    cors.add(app.router.add_route("*", r"/guilds/{id}/members", GuildMembers))
    cors.add(app.router.add_route("*", r"/guilds/{id}/channels", GuildChannels))
    cors.add(app.router.add_route("*", r"/guilds/{id}/roles", GuildRoles))
    cors.add(app.router.add_route("*", r"/users/@me", UserMe))
    cors.add(app.router.add_route("*", "/cogs", CogList))
    cors.add(app.router.add_route("*", r"/cogs/{name}", Cog))
    cors.add(app.router.add_route("*", r"/commands/search", CommandSearch))
    cors.add(app.router.add_route("*", "/auth", Auth))
    cors.add(app.router.add_route("*", "/auth/callback", AuthCallback))
    cors.add(app.router.add_route("*", "/auth/logout", AuthLogout))
    cors.add(app.router.add_route("*", "/locales", Locales))
