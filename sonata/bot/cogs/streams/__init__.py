from typing import TYPE_CHECKING

from .streams import Streams

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Streams(bot))
