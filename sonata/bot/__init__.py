import asyncio
import logging
import os

from sonata.bot.cogs import load_extension
from sonata.bot.core import Sonata


def setup_logger():
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler(
        filename=f"{os.getcwd()}/logs/discord/discord.log", encoding="utf-8", mode="w"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s:%(levelname)s:%(filename)s: %(message)s")
    )
    file_handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("discord")
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
    return logger


async def init_bot(app):
    logger = setup_logger()
    loop = asyncio.get_event_loop()
    bot_config = app["config"]["bot"]
    app["bot"] = Sonata(
        default_prefix=bot_config.default_prefix,
        owner_id=bot_config.owner_id,
        description=bot_config.description,
        db=app.get("db"),
        logger=logger,
        loop=loop,
        config=app["config"],
    )
    for cog in bot_config.cogs:
        load_extension(app["bot"], cog.lower())
    loop.create_task(app["bot"].start(bot_config.discord_token))
    logger.info("Bot started")
