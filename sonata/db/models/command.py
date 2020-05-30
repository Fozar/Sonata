from typing import Optional

from pydantic import BaseModel


class Command(BaseModel):
    name: str
    cog: Optional[str]
    enabled: bool
    invocation_counter: int = 0
    error_count: int = 0
