from typing import TYPE_CHECKING

from .utils import Utils

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Utils(bot))
