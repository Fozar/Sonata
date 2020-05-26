from typing import TYPE_CHECKING

from .general import General

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(General(bot))
