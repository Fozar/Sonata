from datetime import datetime
from typing import Optional, Dict

from sonata.db.models import CreatedAtMixin


class ModlogCase(CreatedAtMixin):
    guild_id: int
    id: int
    action: int
    user_id: int
    target_id: int
    reason: Optional[str]
    expires_at: Optional[datetime]
    expired: Optional[bool]


class ChannelPermissionsCache(CreatedAtMixin):
    guild_id: int
    channel_id: int
    member_id: int
    value: Dict[str, Optional[bool]]
