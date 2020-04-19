import inspect

from discord.ext import commands

from sonata.bot.utils import i18n
from .context import Context
from .errors import NoPremium


class Command(commands.Command):
    def __init__(self, func, **kwargs):
        self.raw_doc = getattr(func, "__doc__", None)
        super().__init__(func, **kwargs)

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


def premium_only():
    """A :func:`.check` that indicates this command must only be used in a premium guild
    context only. Basically, no private messages are allowed when using the command.

    This check raises a special exception, :exc:`.NoPremium` that is inherited from
    :exc:`.CheckFailure`.
    """

    async def predicate(ctx: Context):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"premium": True})
        if not guild["premium"]:
            raise NoPremium()
        return True

    return commands.check(predicate)
