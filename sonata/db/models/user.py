from datetime import datetime
from typing import Optional, List

from .base import CreatedAtMixin, CounterMixin, DiscordConfigModel


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
