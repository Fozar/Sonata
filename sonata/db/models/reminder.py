from datetime import datetime
from typing import Optional

from .base import CreatedAtMixin


class Reminder(CreatedAtMixin):
    id: int
    reminder: str
    expires_at: datetime
    user_id: int
    guild_id: Optional[int]
    channel_id: int
    active: bool = True
