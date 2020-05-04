import json
import pathlib

from .settings import MongoConfig, BotConfig, TwitchConfig, ApiConfig


async def init_config(app):
    with open(
        pathlib.Path(__file__).parent.absolute().joinpath("config.json")
    ) as json_file:
        data = dict(json.load(json_file))
        if not app["debug"]:
            BotConfig.discord_token = data["Bot"]["main_token"]
            BotConfig.dbl_token = data["Bot"]["dbl_token"]
            MongoConfig.username = data["Mongo"]["username"]
            MongoConfig.password = data["Mongo"]["password"]
        else:
            print("DEBUG MODE")
            BotConfig.discord_token = data["Bot"]["test_token"]
        for key, value in data["Twitch"].items():
            setattr(TwitchConfig, key, value)
        for key, value in data["Api"].items():
            setattr(ApiConfig, key, value)
    app["config"] = {
        "bot": BotConfig(),
        "mongo": MongoConfig(),
        "twitch": TwitchConfig(),
        "api": ApiConfig(),
    }
    app["logger"].info("Config initialized")
