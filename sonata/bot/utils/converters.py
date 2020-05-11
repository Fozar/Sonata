import ast
import asyncio
import operator as op
import re
from datetime import timedelta
from decimal import Decimal, ExtendedContext, localcontext
from functools import partial

import flag as f
import pytz
from babel.dates import format_timedelta
from dateparser import search
from discord.ext import commands

from sonata.bot import core
from . import i18n
from ...db.models import ModlogCase


def delete_message_days(days: str) -> int:
    days = int(days)
    if not 0 <= days <= 7:
        raise commands.BadArgument(
            _("The minimum deleted days are 0 and the maximum is 7.")
        )
    return days


def flag_to_locale(flag: str) -> str:
    locale = f.dflagize(flag)
    r = re.compile(r".{2}_" + locale.strip(":"))
    return list(filter(r.match, i18n.LOCALES))[0]


def to_lower(arg: str) -> str:
    return arg.lower()


def validate_locale(arg: str) -> str:
    if arg not in i18n.LOCALES:
        raise commands.BadArgument(_("Locale not found"))
    return arg


def locale_to_flag(locale: str) -> str:
    return f.flag(locale[-2:])


def locale_to_lang(locale: str) -> str:
    return locale[:2]


class EvalExpression(commands.Converter):
    def __init__(self):
        self.parsed = None
        self.fn_name = "_eval_expr"

    def insert_returns(self, body):
        # insert return stmt if the last expression is a expression statement
        if isinstance(body[-1], ast.Expr):
            body[-1] = ast.Return(body[-1].value)
            ast.fix_missing_locations(body[-1])

        # for if statements, we insert returns into the body and the orelse
        if isinstance(body[-1], ast.If):
            self.insert_returns(body[-1].body)
            self.insert_returns(body[-1].orelse)

        # for with blocks, again we insert returns into the body
        if isinstance(body[-1], ast.With):
            self.insert_returns(body[-1].body)

    async def convert(self, ctx: core.Context, argument):
        cmd = argument.strip("` ").splitlines()
        if cmd[0] in ("py", "python"):
            cmd.pop(0)
        # add a layer of indentation
        cmd = "\n".join(f"    {i}" for i in cmd)

        # wrap in async def body
        body = f"async def {self.fn_name}():\n{cmd}"

        self.parsed = ast.parse(body)
        body = self.parsed.body[0].body

        self.insert_returns(body)
        return self


class GlobalChannel(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            # Not found... so fall back to ID + global lookup
            try:
                channel_id = int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(
                    _("Could not find a channel by ID {0}.").format(repr(argument))
                )
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(
                        _("Could not find a channel by ID {0}.").format(repr(argument))
                    )
                return channel


class MathExpression(commands.Converter):
    def __init__(self, timeout: float = 1.0):
        self.operators = {
            ast.Add: op.add,
            ast.Sub: op.sub,
            ast.Mult: op.mul,
            ast.Div: op.truediv,
            ast.Pow: self.power,
            ast.USub: op.neg,
            ast.UAdd: op.pos,
        }
        self.timeout = timeout

    @staticmethod
    def power(a, b):
        if any(abs(n) > 100 for n in [a, b]):
            raise OverflowError(a, b)
        return op.pow(a, b)

    def eval_(self, node):
        if isinstance(node, ast.Num):  # <number>
            return Decimal(str(node.n))
        elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
            return self.operators[type(node.op)](
                self.eval_(node.left), self.eval_(node.right)
            )
        elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
            return self.operators[type(node.op)](self.eval_(node.operand))
        elif isinstance(node, ast.Name):
            return Decimal(node.id)
        else:
            raise commands.BadArgument(_("Invalid expression"))

    def eval_expr(self, expr):
        try:
            with localcontext(ExtendedContext):
                return self.eval_(ast.parse(expr, mode="eval").body)
        except SyntaxError:
            raise commands.BadArgument(_("Invalid expression"))

    async def convert(self, ctx: core.Context, argument):
        argument = argument.strip(" `\n").replace(" ", "").replace("^", "**")
        eval_expr = partial(self.eval_expr, argument)
        with ctx.typing():
            try:
                result = await asyncio.wait_for(
                    ctx.bot.loop.run_in_executor(ctx.pool, eval_expr),
                    timeout=self.timeout,
                    loop=ctx.bot.loop,
                )
            except asyncio.TimeoutError:
                raise commands.BadArgument(
                    _("Timeout exceeded: {0}s").format(self.timeout)
                )
            except OverflowError as e:
                raise commands.BadArgument(
                    _("Range exceeded: {0} ** {1}").format(e.args[0], e.args[1])
                )
        return result


class ModeratedMember(commands.MemberConverter):
    async def convert(self, ctx: core.Context, argument):
        member = await super().convert(ctx, argument)
        if ctx.author == member:
            raise commands.BadArgument(
                _('Member "{0}" is the author of the message.').format(str(member))
            )
        if ctx.guild.me == member:
            raise commands.BadArgument(_('Member "{0}" is me.').format(str(member)))
        if ctx.guild.owner == member:
            raise commands.BadArgument(
                _('Member "{0}" is the guild owner.').format(str(member))
            )
        if ctx.guild.owner == ctx.author:
            return member
        if ctx.author.top_role <= member.top_role:
            raise commands.BadArgument(
                _('Member "{0}" is above moderator in the role hierarchy.').format(
                    str(member)
                )
            )
        if ctx.guild.me.top_role <= member.top_role:
            raise commands.BadArgument(
                _('Member "{0}" is above me in the role hierarchy.').format(str(member))
            )
        if ctx.author.guild_permissions.administrator:
            return member
        if member.guild_permissions.administrator:
            raise commands.BadArgument(
                _('Member "{0}" is guild administrator.').format(str(member))
            )
        guild = await ctx.db.guilds.find_one(
            {"id": ctx.guild.id}, {"admin_roles": True, "mod_roles": True}
        )
        if not guild:
            return member

        if guild.get("admin_roles") and member.id in guild["admin_roles"]:
            raise commands.BadArgument(
                _('Member "{0}" is guild administrator.').format(str(member))
            )
        if guild.get("mod_roles") and member.id in guild["mod_roles"]:
            raise commands.BadArgument(
                _('Member "{0}" is guild moderator.').format(str(member))
            )
        return member


class ModlogCaseConverter(commands.IDConverter):
    async def convert(self, ctx: core.Context, argument):
        match = self._get_id_match(argument)
        if match is None:
            raise commands.BadArgument(_("Invalid ID."))
        case = await ctx.db.modlog_cases.find_one(
            {"guild_id": ctx.guild.id, "id": int(argument)}
        )
        if not case:
            raise commands.BadArgument(_("Case not found."))

        return ModlogCase(**case)


class TagName(commands.clean_content):
    def __init__(self, *, lower: bool = True):
        self.lower = lower
        super().__init__()

    async def convert(self, ctx: core.Context, argument):
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()

        if not lower:
            raise commands.BadArgument(_("Missing tag name."))

        if len(lower) > 100:
            raise commands.BadArgument(_("Tag name is a maximum of 100 characters."))

        first_word, __, __ = lower.partition(" ")

        root = ctx.bot.get_command("tag")
        if first_word in root.all_commands:
            raise commands.BadArgument(_("This tag name starts with a reserved word."))

        return converted if not self.lower else lower


class UserFriendlyTime(commands.Converter):
    def __init__(
        self,
        converter=None,
        default=None,
        future: bool = True,
        past: bool = False,
        max_delta: int = 86400 * 365 * 5,
    ):
        if isinstance(converter, type) and issubclass(converter, commands.Converter):
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):
            raise TypeError("commands.Converter subclass necessary.")

        self.converter = converter
        self.default = default
        self.future = future
        self.past = past
        self.max_delta = timedelta(seconds=max_delta)
        self.arg = None
        self.dt = None

    async def convert(self, ctx: core.Context, argument):
        me = _("me")  # Like as "Remind me..."
        if argument.startswith(me):
            argument = argument[len(me) :].strip()
        languages = [locale_to_lang(locale) for locale in i18n.LOCALES]
        date = search.search_dates(argument, languages=languages)
        if date is None:
            raise commands.BadArgument(_("Could not recognize the date."))

        try:
            now = ctx.message.created_at.replace(tzinfo=pytz.utc)
            date = date[0]
            when = date[1].astimezone(pytz.utc)
        except OSError:
            raise commands.BadArgument(_("An error occurred converting the date."))
        if not self.past and when <= now:
            raise commands.BadArgument(_("This time is in the past."))
        if not self.future and when > now:
            raise commands.BadArgument(_("This time is in the future."))
        if when - now > self.max_delta:
            raise commands.BadArgument(
                _("Maximum timedelta: {0}").format(
                    format_timedelta(self.max_delta, locale=ctx.locale)
                )
            )
        self.dt = when

        remaining = (argument.replace(date[0], "")).strip()
        if not remaining:
            if not self.default:
                raise commands.BadArgument(
                    _("Missing argument before or after the time.")
                )
            else:
                self.arg = self.default

        if self.converter is not None:
            self.arg = await self.converter.convert(ctx, remaining)
        else:
            self.arg = remaining

        return self
