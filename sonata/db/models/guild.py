from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .base import BWList, DiscordConfigModel, BaseAlertConfig


class Channel(DiscordConfigModel):
    pass


class Greeting(BaseModel):
    channel_id: int = None
    message: str = None


class GuildUpdate(DiscordConfigModel):
    dm_help: bool = False
    auto_lvl_msg: bool = False
    delete_commands: bool = False
    greeting: Greeting = Greeting()
    admin_roles: List[int] = []
    mod_roles: List[int] = []
    disabled_cogs: List[str] = []
    disabled_commands: List[str] = []
    blacklist: BWList = BWList()
    whitelist: BWList = BWList()


class Guild(CreatedAtMixin, GuildUpdate):
    owner_id: int
    premium: bool = False
    last_message_at: datetime = None
    modlog: Optional[int] = None
    alerts: Optional[BaseAlertConfig] = BaseAlertConfig()
    channels: List[Channel] = []
    left: Optional[datetime] = None
