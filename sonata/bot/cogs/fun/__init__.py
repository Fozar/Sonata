from typing import TYPE_CHECKING

from .fun import Fun

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Fun(bot))
