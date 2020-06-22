from datetime import datetime
from typing import Optional, List

from discord.ext import commands
from pydantic import BaseModel, validator

from sonata.bot.utils.converters import validate_locale


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
    custom_prefix: Optional[str] = "!"

    @validator('locale')
    def locale_validator(cls, v: str):
        try:
            return validate_locale(v)
        except commands.BadArgument:
            raise ValueError("locale not found")

    @validator('custom_prefix')
    def prefix_validator(cls, v: str):
        v = v.strip()
        if len(v) > 20:
            raise ValueError("prefix is too long")
        if len(v) == 0:
            raise ValueError("prefix is a required")
        return v


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
