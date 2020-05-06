from .guild import Guild


async def init_views(app):
    app["cors"].add(app.router.add_route("*", "/guilds", Guild))
