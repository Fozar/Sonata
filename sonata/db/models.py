from datetime import datetime
from typing import Optional, List

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


class User(DiscordConfigModel, CounterMixin):
    about: Optional[str] = None
    exp: int = 0
    lvl: int = 0
    last_exp_at: datetime = None
    guilds: List[int] = []


class Channel(DiscordConfigModel):
    pass


class Guild(DiscordConfigModel, CounterMixin):
    last_message_at: datetime = None
    premium: bool = False
    dm_help: bool = False
    leveling: bool = True
    admin_role: Optional[int] = None
    mod_role: Optional[int] = None
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
