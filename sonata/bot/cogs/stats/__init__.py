from typing import TYPE_CHECKING

from .stats import Stats

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Stats(bot))
