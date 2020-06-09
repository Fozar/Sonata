import asyncio

from aiohttp_security import setup as setup_security, SessionIdentityPolicy
from aiohttp_session import setup as setup_session
from aiohttp_session_mongo import MongoStorage
from motor import motor_asyncio as motorio

from sonata.db.logging import setup_logger
from sonata.db.models.db_auth import DBAuthorizationPolicy


async def close_mongo(app):
    app["db"].client.close()


async def init_db(app):
    setup_logger()
    app["db"] = db = motorio.AsyncIOMotorClient(
        app["config"]["mongo"].url, appname="sonata", io_loop=asyncio.get_event_loop()
    )[app["config"]["mongo"].database]
    app["logger"].info("Mongo connected.")
    app.on_cleanup.append(close_mongo)
    session_collection = db.sessions
    setup_session(app, MongoStorage(session_collection, max_age=3600 * 24 * 30))
    setup_security(app, SessionIdentityPolicy(), DBAuthorizationPolicy(db))
