from typing import TYPE_CHECKING

from .reminder import Reminder

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Reminder(bot))
