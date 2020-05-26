from typing import TYPE_CHECKING

from .mod import Mod

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Mod(bot))
