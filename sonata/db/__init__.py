import asyncio

from motor import motor_asyncio as motorio

from sonata.db.logging import setup_logger


async def close_mongo(app):
    app["db"].client.close()


async def init_db(app):
    setup_logger()
    app["db"] = motorio.AsyncIOMotorClient(
        app["config"]["mongo"].url, appname="sonata", io_loop=asyncio.get_event_loop()
    )[app["config"]["mongo"].database]
    app["logger"].info("Mongo connected.")
    app.on_cleanup.append(close_mongo)
