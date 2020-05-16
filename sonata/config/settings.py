from typing import FrozenSet


class BotConfig:
    discord_token: str = None
    dbl_token: str = None
    owner_id: int = 149722383165423616
    description: str = _(
        """Sonata is a multi-functional polyglot bot. The bot has many modules for \
        entertaining members, providing useful utilities, useful information from a \
        worldwide network and much more.
        
        The sonata has a global leveling system. Users can gain experience for activity \
        and increase levels on different servers to which the bot is connected. This \
        red-haired girl keeps various statistics. Thanks to this, you can find out the \
        average number of messages per day in the guild, how many teams were used, which \
        emoji is the most popular, etc. A brief of each of the modules:
        
        `General` Main commands and information.
        `Admin` This module is responsible for the unique behavior of the bot on your \
        server. You can disable and enable modules and commands, change the language and \
        prefix of the bot, etc.
        `Mod` Using this module, moderators can ban, unban, kick members, bulk delete \
        flood, etc. All actions can be logged in the modlog.
        `Emoji` The module allows you to get detailed information about emoji, and also \
        keeps statistics on the use of emoji.
        `Reminder` This module allows you to create reminders for a specific event after \
        a certain amount of time.
        `Utils` Various useful utilities, such as a calculator, weather and virus info.
        `Stats` The module is responsible for general statistics and level system. It \
        has user rank card command and a leaderboard.
        `Locale` This module allows you to set the language in direct messages and \
        display a list of supported languages.
        `Fun` A large set of entertainment teams. Everything from 8ball to cat pictures. \
        Also has an advanced version of roll.
        """
    )
    default_prefix: str = "!"
    core_cogs: FrozenSet[str] = frozenset(
        {"Locale", "Owner", "General", "Admin", "Stats"}
    )
    other_cogs: FrozenSet[str] = frozenset(
        {"Fun", "Reminder", "Utils", "Emoji", "Mod", "Tags", "Streams"}
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
