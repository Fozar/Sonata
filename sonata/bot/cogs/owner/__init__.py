from typing import TYPE_CHECKING

from .owner import Owner

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Owner(bot))
