import asyncio
import logging
import os
from logging import handlers

from aiohttp import ClientSession

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


async def get_twitch_bearer_token(twitch_config):
    async with ClientSession() as session:
        response = await session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": twitch_config.client_id,
                "client_secret": twitch_config.client_secret,
                "grant_type": "client_credentials",
            },
        )
        body = await response.json()
        return body["access_token"]


async def init_bot(app):
    logger = setup_logger()
    loop = asyncio.get_event_loop()
    bot_config = app["config"]["bot"]
    twitch_bearer_token = await get_twitch_bearer_token(app["config"]["twitch"])
    app["bot"] = Sonata(
        logger=logger, app=app, loop=loop, twitch_bearer_token=twitch_bearer_token
    )
    for cog in bot_config.cogs:
        load_extension(app["bot"], cog.lower())
    loop.create_task(app["bot"].start())
