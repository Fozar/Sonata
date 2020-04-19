from motor import motor_asyncio as motorio

from sonata.config import MongoConfig

mongo_config = MongoConfig()


async def close_mongo(app):
    app["db"].client.close()


async def init_db(app):
    app["db"] = motorio.AsyncIOMotorClient(mongo_config.url)[mongo_config.database]
    print("Mongo connected.")
    app.on_cleanup.append(close_mongo)
