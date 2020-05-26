from typing import TYPE_CHECKING

from .admin import Admin

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Admin(bot))
