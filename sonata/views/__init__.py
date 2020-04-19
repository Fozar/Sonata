from aiohttp import web

from .ping import Ping


async def init_views(app):
    app.add_routes([web.view("/", Ping)])
