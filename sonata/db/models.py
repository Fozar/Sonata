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


class Guild(DiscordConfigModel):
    premium: bool = False
    dm_help: bool = False
    auto_lvl_msg: bool = True
    greeting: Optional[Greeting] = None
    last_message_at: datetime = None
    admin_roles: List[int] = []
    mod_roles: List[int] = []
    modlog: Optional[int] = None
    alerts: Optional[int] = None
    disabled_cogs: List[str] = []
    disabled_commands: List[str] = []
    channels: List[Channel] = []
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


class ChannelPermissionsCache(CreatedAtMixin):
    guild_id: int
    channel_id: int
    member_id: int
    value: Dict[str, Optional[bool]]
