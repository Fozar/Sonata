import asyncio
import logging
import os

from aiohttp import web

from sonata import bot, db
from sonata.bot import init_bot
from sonata.config import init_config
from sonata.db import init_db
from sonata.views import init_views

try:
    import uvloop
except ImportError:
    uvloop = None  # Windows
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


def setup_logger():
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler(
        filename=f"{os.getcwd()}/logs/app/app.log", encoding="utf-8", mode="w"
    )
    stream_handler.setLevel(logging.INFO)
    logger = logging.getLogger("aiohttp.access")
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
    return logger


def create_app(debug: bool = False):
    logger = setup_logger()
    logger.info("Create application")
    app = web.Application()
    app["debug"] = debug
    logger.info("Append modules")
    app.on_startup.append(init_config)
    app.on_startup.append(init_db)
    app.on_startup.append(init_bot)
    app.on_startup.append(init_views)
    logger.info("Run server")
    web.run_app(app, host="localhost", port=8080)


if __name__ == "__main__":
    create_app()
