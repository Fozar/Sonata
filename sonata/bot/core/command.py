import inspect

from discord.ext import commands

from sonata.bot.utils import i18n


class Command(commands.Command):
    def __init__(self, func, **kwargs):
        self._examples = kwargs.get('examples')
        self.raw_doc = getattr(func, "__doc__", None)
        super().__init__(func, **kwargs)

    def to_dict(self):
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "aliases": self.aliases,
            "signature": self.signature,
            "help": self.help,
            "brief": self.short_doc,
            "cog": self.cog_name,
        }

    @property
    def examples(self):
        return list(map(_, self._examples))

    @examples.setter
    def examples(self, value):
        self._examples = value

    @property
    def brief(self):
        """Applies locale when getting"""
        return _(self._brief)

    @brief.setter
    def brief(self, value):
        self._brief = value

    @property
    def help(self):
        """Applies locale when getting"""
        try:
            return inspect.cleandoc(_(self.raw_doc))
        except AttributeError:
            return _(self._help)

    @help.setter
    def help(self, value):
        self._help = value


class Group(Command, commands.Group):
    def to_dict(self):
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "aliases": self.aliases,
            "signature": self.signature,
            "help": self.help,
            "brief": self.short_doc,
            "cog": self.cog_name,
            "commands": [c.to_dict() for c in sorted(self.commands, key=lambda c: c.name)]
        }

    def command(self, *args, **kwargs):
        """A shortcut decorator that invokes :func:`.command` and adds it to
        the internal command list via :meth:`~.GroupMixin.add_command`.
        """

        def decorator(func):
            kwargs.setdefault("parent", self)
            result = command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(self, *args, **kwargs):
        """A shortcut decorator that invokes :func:`.group` and adds it to
        the internal command list via :meth:`~.GroupMixin.add_command`.
        """

        def decorator(func):
            kwargs.setdefault("parent", self)
            result = group(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator


def command(name=None, cls=None, **attrs):
    if cls is None:
        cls = Command

    def decorator(func):
        func = i18n.i18n_docstring(func)
        if isinstance(func, Command):
            raise TypeError("Callback is already a command.")
        return cls(func, name=name, **attrs)

    return decorator


def group(name=None, **attrs):
    attrs.setdefault("cls", Group)
    return command(name=name, **attrs)
