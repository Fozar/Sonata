from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, validator


class CreatedAtMixin(BaseModel):
    created_at: datetime = None

    @validator("created_at", pre=True, always=True)
    def set_created_at_now(cls, v):
        return v or datetime.utcnow()


class CounterMixin(BaseModel):
    total_messages: int = 0
    commands_invoked: int = 0


class DiscordModel(BaseModel):
    id: int
    name: str


class DiscordConfigModel(CreatedAtMixin, DiscordModel):
    locale: str = "en_US"
    custom_prefix: Optional[str] = None


class UserStats(CreatedAtMixin, CounterMixin):
    guild_id: int
    user_id: int
    exp: int = 0
    lvl: int = 0
    last_exp_at: datetime = None
    auto_lvl_msg: bool = True


class User(DiscordConfigModel):
    about: Optional[str] = None
    guilds: List[int] = []


class Channel(DiscordConfigModel):
    pass


class Greeting(BaseModel):
    channel_id: int
    message: str


class BWList(BaseModel):
    enabled: bool = False
    channels: List[int] = []


class BaseAlertConfig(BaseModel):
    enabled: bool = False
    message: str = None
    channel: int = None
    mention: str = None


class Guild(DiscordConfigModel):
    owner_id: int
    premium: bool = False
    dm_help: bool = False
    auto_lvl_msg: bool = False
    greeting: Optional[Greeting] = None
    last_message_at: datetime = None
    admin_roles: List[int] = []
    mod_roles: List[int] = []
    modlog: Optional[int] = None
    alerts: Optional[BaseAlertConfig] = BaseAlertConfig()
    disabled_cogs: List[str] = []
    disabled_commands: List[str] = []
    channels: List[Channel] = []
    blacklist: BWList = BWList()
    whitelist: BWList = BWList()
    left: Optional[datetime] = None


class Command(BaseModel):
    name: str
    cog: Optional[str]
    enabled: bool
    invocation_counter: int = 0
    error_count: int = 0


class Reminder(CreatedAtMixin):
    id: int
    reminder: str
    expires_at: datetime
    user_id: int
    guild_id: Optional[int]
    channel_id: int
    active: bool = True


class DailyStats(CounterMixin):
    date: datetime
    guild_id: int


class EmojiStats(CreatedAtMixin):
    id: int
    guild_id: int
    total: int


class ModlogCase(CreatedAtMixin):
    guild_id: int
    id: int
    action: int
    user_id: int
    target_id: int
    reason: Optional[str]
    expires_at: Optional[datetime]
    expired: Optional[bool]


class ChannelPermissionsCache(CreatedAtMixin):
    guild_id: int
    channel_id: int
    member_id: int
    value: Dict[str, Optional[bool]]


class TagBase(CreatedAtMixin):
    owner_id: int
    uses: int = 0


class TagAlias(TagBase):
    alias: str


class Tag(TagBase):
    name: str
    aliases: List[TagAlias] = []
    content: str
    guild_id: int
    language: str = "en"


class SubscriptionAlertConfig(BaseAlertConfig):
    enabled: bool = True
    id: int
    message_id: int = None


class TwitchSubscription(CreatedAtMixin):
    guilds: List[SubscriptionAlertConfig]
    id: str
    login: str
    topic: str
    callback: str
    secret: str = None
    expires_at: datetime = None
    verified: bool = False
