from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .base import BWList, DiscordConfigModel, BaseAlertConfig


class Channel(DiscordConfigModel):
    pass


class Greeting(BaseModel):
    channel_id: int = None
    message: str = None


class Guild(DiscordConfigModel):
    owner_id: int
    premium: bool = False
    dm_help: bool = False
    auto_lvl_msg: bool = False
    delete_commands: bool = False
    greeting: Optional[Greeting] = Greeting()
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
