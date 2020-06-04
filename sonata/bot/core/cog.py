import discord
from discord.ext import commands


class CogMeta(commands.CogMeta):
    def __new__(mcs, *args, **kwargs):
        name, bases, attrs = args
        attrs["__cog_description__"] = kwargs.pop("description", None)
        attrs["__cog_colour__"] = kwargs.pop("colour", kwargs.pop("color", None))
        mcs.instance = super().__new__(mcs, name, bases, attrs, **kwargs)
        return mcs.instance


class Cog(commands.Cog, metaclass=CogMeta):
    def to_dict(self):
        return {
            "qualified_name": self.qualified_name,
            "description": self.description,
            "commands": [
                c.to_dict()
                for c in sorted(self.get_commands(), key=lambda c: c.name)
                if c.enabled and not c.hidden
            ],
        }

    @property
    def colour(self):
        if hasattr(self, "__cog_colour__") and isinstance(
            self.__cog_colour__, discord.Colour
        ):
            return self.__cog_colour__

        return discord.Colour(0x9B9B9B)

    @property
    def description(self):
        """:class:`str`: Returns the cog's description."""
        if hasattr(self, "__cog_description__") and self.__cog_description__:
            return _(self.__cog_description__)

        return super().description
