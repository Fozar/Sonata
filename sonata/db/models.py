from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, validator, Field


class CounterMixin(BaseModel):
    total_messages: int = 0
    commands_invoked: int = 0


class DiscordModel(BaseModel):
    id: int
    name: str


class DiscordConfigModel(DiscordModel):
    locale: str = "en_US"
    custom_prefix: Optional[str] = None
    created_at: datetime = None

    @validator("created_at", pre=True, always=True)
    def set_created_at_now(cls, v):
        return v or datetime.utcnow()


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


class Command(BaseModel):
    name: str
    cog: Optional[str]
    enabled: bool
    invocation_counter: int = 0
    error_count: int = 0
