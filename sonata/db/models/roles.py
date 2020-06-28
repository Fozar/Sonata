from typing import List, Union

from pydantic import BaseModel


class RoleEmoji(BaseModel):
    emoji: Union[int, str]
    role: int


class RoleMenu(BaseModel):
    guild_id: int
    name: str
    roles: List[RoleEmoji]
    messages: List[int] = []
