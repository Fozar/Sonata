from typing import TYPE_CHECKING

from .locale import Locale

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Locale(bot))
