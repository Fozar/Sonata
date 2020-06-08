from typing import FrozenSet


class BotConfig:
    discord_token: str = None
    client_secret: str = None
    dbl_token: str = None
    sdc_token: str = None
    owner_id: int = 149722383165423616
    description: str = _(
        "Sonata is a multi-functional polyglot bot. The bot has many modules for "
        "entertaining members, moderation, providing useful information and utilities "
        "and much more."
    )
    default_prefix: str = "!"
    core_cogs: FrozenSet[str] = frozenset({"Locale", "Owner", "General", "Admin"})
    other_cogs: FrozenSet[str] = frozenset(
        {"Fun", "Reminder", "Utils", "Emoji", "Mod", "Tags", "Streams", "Stats"}
    )

    @property
    def cogs(self):
        return self.core_cogs | self.other_cogs


class MongoConfig:
    host: str = "localhost"
    port: str = "27017"
    username: str = None
    password: str = None
    database: str = "sonata"

    @property
    def url(self):
        url = "mongodb://"
        if self.username and self.password:
            url += f"{self.username}:{self.password}@"
        return url + f"{self.host}:{self.port}/"

    @property
    def db_url(self):
        return self.url + self.database


class TwitchConfig:
    client_id: str = None
    bearer_token: str = None
    hub_secret: str = None


class ApiConfig:
    open_weather: str = None  # https://openweathermap.org/api
    random_org: str = None  # https://www.random.org/
    cat_api: str = None  # https://docs.thecatapi.com/


class Yandex:
    translate: str = None  # https://yandex.ru/dev/translate/doc/dg/
