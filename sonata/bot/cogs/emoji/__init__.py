from typing import TYPE_CHECKING

from .emoji import Emoji

if TYPE_CHECKING:
    from ... import Sonata


def setup(bot: "Sonata"):
    bot.add_cog(Emoji(bot))
