from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .base import DiscordConfigModel, BaseAlertConfig


class Channel(DiscordConfigModel):
    pass


class Greeting(BaseModel):
    channel_id: int
    message: str


class BWList(BaseModel):
    enabled: bool = False
    channels: List[int] = []


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