from typing import List

from sonata.db.models import CreatedAtMixin


class TagBase(CreatedAtMixin):
    owner_id: int
    uses: int = 0


class TagAlias(TagBase):
    alias: str


class Tag(TagBase):
    name: str
    aliases: List[TagAlias] = []
    content: str
    guild_id: int
    language: str = "en"
