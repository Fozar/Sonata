from datetime import datetime
from typing import List

from .base import BaseAlertConfig, Mention, CreatedAtMixin


class CustomMention(Mention):
    inherit: bool = True


class SubscriptionAlertConfig(BaseAlertConfig):
    enabled: bool = True
    id: int
    message_id: int = None
    mention: CustomMention = CustomMention()


class TwitchSubscriptionStatus(CreatedAtMixin):
    guilds: List[SubscriptionAlertConfig]
    id: str
    login: str
    topic: str
    callback: str
    expires_at: datetime = None
    verified: bool = False
