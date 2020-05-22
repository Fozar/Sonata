import asyncio
import logging
import os
from logging import handlers

from sonata.bot.cogs import load_extension
from sonata.bot.core import Sonata


def setup_logger():
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] - %(filename)s - %(message)s")
    )
    stream_handler.setLevel(logging.INFO)
    file_handler = handlers.TimedRotatingFileHandler(
        filename=os.getcwd() + "/logs/discord/discord.log",
        when="midnight",
        backupCount=1,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] - %(filename)s - %(message)s")
    )
    file_handler.setLevel(logging.INFO)
    logger = logging.getLogger("discord")
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    return logger


async def init_bot(app):
    logger = setup_logger()
    loop = asyncio.get_event_loop()
    bot_config = app["config"]["bot"]
    app["bot"] = Sonata(logger=logger, app=app, loop=loop)
    for cog in bot_config.cogs:
        load_extension(app["bot"], cog.lower())
    loop.create_task(app["bot"].start())
