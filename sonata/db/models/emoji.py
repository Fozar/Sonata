from .base import CreatedAtMixin


class EmojiStats(CreatedAtMixin):
    id: int
    guild_id: int
    total: int
