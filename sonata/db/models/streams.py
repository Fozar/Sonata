from datetime import datetime
from typing import List

from pydantic import BaseModel

from .base import BaseAlertConfig, Mention, CreatedAtMixin, BWList


class CustomMention(Mention):
    inherit: bool = True


class BaseFilter(BaseModel):
    blacklist: BWList = BWList()
    whitelist: BWList = BWList()


class Filter(BaseModel):
    game: BaseFilter = BaseFilter()
    title: BaseFilter = BaseFilter()


class SubscriptionAlertConfig(BaseAlertConfig):
    enabled: bool = True
    id: int
    message_id: str = None
    mention: CustomMention = CustomMention()
    filter: Filter = Filter()


class TwitchSubscriptionStatus(CreatedAtMixin):
    guilds: List[SubscriptionAlertConfig]
    id: str
    login: str
    topic: str
    callback: str
    expires_at: datetime = None
    verified: bool = False
