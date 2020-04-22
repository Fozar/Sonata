import ast
import copy
from typing import Optional

import discord
from discord.ext import commands

from sonata.bot import core
from sonata.bot.cogs import load_extension, unload_extension, reload_extension
from sonata.bot.utils.converters import GlobalChannel
from sonata.bot.utils.misc import to_lower


class Owner(
    core.Cog, description=_("""Commands of bot owner"""), colour=discord.Colour(0x1)
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self._last_result = None

    async def cog_check(self, ctx: core.Context):
        return await self.sonata.is_owner(ctx.author)

    @core.command()
    async def sudo(
        self,
        ctx: core.Context,
        channel: Optional[GlobalChannel],
        who: discord.User,
        *,
        command: str,
    ):
        """Выполняет команду от имени определенного участника"""
        msg = copy.copy(ctx.message)
        channel = channel or ctx.channel
        msg.channel = channel
        msg.author = channel.guild.get_member(who.id) or who
        msg.content = ctx.prefix + command
        new_ctx = await self.sonata.get_context(msg, cls=type(ctx))
        await self.sonata.invoke(new_ctx)

    @core.command()
    async def repeat(self, ctx, times: int, *, command: str):
        """Повторяет команду указанное количество раз"""
        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.sonata.get_context(msg, cls=type(ctx))

        for i in range(times):
            await new_ctx.reinvoke()

    async def cog_command_error(self, ctx: core.Context, error):
        original = error.original
        if isinstance(original, commands.ExtensionNotFound):
            await ctx.send(f"Я не нашла модуль: **{original.name}**!")
        elif isinstance(original, commands.ExtensionAlreadyLoaded):
            await ctx.send(f"Модуль уже подключен: **{original.name}**!")
        elif isinstance(original, commands.ExtensionNotLoaded):
            await ctx.send(f"Я не подключала модуль: **{original.name}**!")
        elif isinstance(original, commands.NoEntryPointError):
            await ctx.send(
                f"В расширении модуля **{original.name}** отсутсвует функция запуска."
            )
        elif isinstance(original, commands.ExtensionFailed):
            await ctx.send(
                f"В модуле **{original.name}** или его функции запуска произошла ошибка:\n{original.original}"
            )
        await self.sonata.change_presence(status=discord.Status.dnd)

    @core.command()
    async def ping(self, ctx: core.Context):
        """Pong!"""
        await ctx.send(f"Pong! {round(self.sonata.latency * 1000)}ms")

    @core.group()
    async def cogs(self, ctx: core.Context):
        """Выводит список подключенных модулей"""
        if ctx.invoked_subcommand is not None:
            return

        loaded_cogs = list(self.sonata.cogs.keys())
        if not loaded_cogs:
            await ctx.send("Нет подключенных модулей!")
            return

        content = "```"
        if loaded_cogs:
            content += f"Подключенные модули:\n{', '.join(loaded_cogs)}\n"
        content += "```"
        await ctx.send(content)

    @cogs.command()
    async def load(self, ctx: core.Context, cog_name: to_lower):
        """Подключает модуль"""
        await self.sonata.change_presence(status=discord.Status.idle)
        load_extension(self.sonata, cog_name)
        await ctx.send(f"Подключила модуль: **{cog_name}**.")
        await self.sonata.change_presence(status=discord.Status.dnd)

    @cogs.command()
    async def unload(self, ctx: core.Context, cog_name: to_lower):
        """Отключает модуль"""
        if cog_name == to_lower(self.qualified_name):
            await ctx.send("Этот модуль не может быть отключен")
            return

        unload_extension(self.sonata, cog_name)
        await ctx.send(f"Отключила модуль: **{cog_name}**.")

    @cogs.command()
    async def reload(self, ctx: core.Context, cog_name: to_lower):
        """Переподключает модуль"""
        await self.sonata.change_presence(status=discord.Status.idle)
        reload_extension(self.sonata, cog_name)
        await ctx.send(f"Переподключила модуль: **{cog_name}**.")
        await self.sonata.change_presence(status=discord.Status.dnd)

    @core.command()
    async def uptime(self, ctx: core.Context):
        """Показывает время с момента запуска бота"""
        await ctx.send(self.sonata.uptime)

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

    @core.command(name="eval")
    async def eval_fn(self, ctx: core.Context, *, cmd):
        """Evaluates input.
        Input is interpreted as newline separated statements.
        If the last statement is an expression, that is the return value.
        Usable globals:
          - `bot`: the bot instance
          - `discord`: the discord module
          - `commands`: the discord.ext.commands module
          - `ctx`: the invocation context
          - `__import__`: the builtin `__import__` function
        Such that `>eval 1 + 1` gives `2` as the result.
        The following invocation will cause the bot to send the text '9'
        to the channel of invocation and return '3' as the result of evaluating
        >eval ```py
        a = 1 + 2
        b = a * 2
        await ctx.send(a + b)
        a
        ```
        """
        fn_name = "_eval_expr"

        cmd = cmd.strip("` ").splitlines()
        if cmd[0] in ("py", "python"):
            cmd.pop(0)
        # add a layer of indentation
        cmd = "\n".join(f"    {i}" for i in cmd)

        # wrap in async def body
        body = f"async def {fn_name}():\n{cmd}"

        parsed = ast.parse(body)
        body = parsed.body[0].body

        self.insert_returns(body)

        env = {
            "bot": ctx.bot,
            "discord": discord,
            "commands": commands,
            "ctx": ctx,
            "__import__": __import__,
            "_": self._last_result,
        }
        exec(compile(parsed, filename="<ast>", mode="exec"), env)
        try:
            result = await eval(f"{fn_name}()", env)
        except Exception as e:
            await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")
        else:
            self._last_result = result
            await ctx.send(f"```py\n{result}\n```")
