from motor import motor_asyncio as motorio


async def close_mongo(app):
    app["db"].client.close()


async def init_db(app):
    app["db"] = motorio.AsyncIOMotorClient(app["config"]["mongo"].url)[
        app["config"]["mongo"].database
    ]
    print("Mongo connected.")
    app.on_cleanup.append(close_mongo)
