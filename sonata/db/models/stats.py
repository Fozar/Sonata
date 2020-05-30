from datetime import datetime

from .base import CounterMixin


class DailyStats(CounterMixin):
    date: datetime
    guild_id: int
