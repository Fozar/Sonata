from typing import TYPE_CHECKING

from .tags import Tags

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Tags(bot))
