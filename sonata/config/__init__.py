import json
import pathlib

from .settings import MongoConfig, BotConfig, TwitchConfig, ApiConfig, Yandex


async def init_config(app):
    with open(
        pathlib.Path(__file__).parent.absolute().joinpath("config.json")
    ) as json_file:
        data = dict(json.load(json_file))
        if not app["debug"]:
            BotConfig.discord_token = data["Bot"]["main_token"]
            BotConfig.dbl_token = data["Bot"]["dbl_token"]
            BotConfig.sdc_token = data["Bot"]["sdc_token"]
            MongoConfig.username = data["Mongo"]["username"]
            MongoConfig.password = data["Mongo"]["password"]
        else:
            print("DEBUG MODE")
            BotConfig.discord_token = data["Bot"]["test_token"]
        BotConfig.client_secret = data["Bot"]["client_secret"]
        for key, value in data["Twitch"].items():
            setattr(TwitchConfig, key, value)
        for key, value in data["Api"].items():
            setattr(ApiConfig, key, value)
        for key, value in data["Yandex"].items():
            setattr(Yandex, key, value)
    app["config"] = {
        "bot": BotConfig(),
        "mongo": MongoConfig(),
        "twitch": TwitchConfig(),
        "api": ApiConfig(),
        "yandex": Yandex(),
    }
    app["logger"].info("Config initialized")
