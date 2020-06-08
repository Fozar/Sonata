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


class Mention(BaseModel):
    enabled: bool = False
    value: Optional[str] = None


class BaseAlertConfig(BaseModel):
    enabled: bool = False
    message: Optional[str] = None
    close_message: Optional[str] = None
    channel: Optional[int] = None
    mention: Mention = Mention()


class BWList(BaseModel):
    enabled: bool = False
    items: List[int] = []
