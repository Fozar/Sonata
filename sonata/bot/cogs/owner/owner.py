import asyncio
import copy
import inspect
import os
import platform
import subprocess
import time
from datetime import timedelta
from functools import partial
from typing import Optional

import discord
import psutil
from babel.dates import format_timedelta
from discord.ext import commands

from sonata.bot import core
from sonata.bot.cogs import load_extension, unload_extension, reload_extension
from sonata.bot.utils.converters import GlobalChannel, to_lower, EvalExpression


class Owner(
    core.Cog, colour=discord.Colour.purple(),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        self._last_result = None

    async def cog_check(self, ctx: core.Context):
        return await self.sonata.is_owner(ctx.author)

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            result = await process.communicate()
        except NotImplementedError:
            with subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) as p:
                result = await self.sonata.loop.run_in_executor(
                    self.sonata.pool, p.communicate
                )
        try:
            return [output.decode() for output in result]
        except UnicodeDecodeError:
            return [output.decode("CP866") for output in result]

    @core.group()
    async def blacklist(self, ctx: core.Context):
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @blacklist.command(name="add")
    async def blacklist_add(
        self, ctx: core.Context, id: int, *, reason: Optional[str] = None
    ):
        await ctx.db.blacklist.update_one(
            {"id": id}, {"$setOnInsert": {"reason": reason}}, upsert=True
        )
        await ctx.inform(f"ID {id} добавлен в черный список.")

    @blacklist.command(name="remove")
    async def blacklist_remove(self, ctx: core.Context, id: int):
        await ctx.db.blacklist.delete_many({"id": id})
        await ctx.inform(f"ID {id} удален из черного списка.")

    @core.command()
    async def sudo(
        self,
        ctx: core.Context,
        channel: Optional[GlobalChannel],
        who: discord.User,
        *,
        command: str,
    ):
        _(
            """Executes a command on behalf of a specific member in a specific channel."""
        )
        msg = copy.copy(ctx.message)
        channel = channel or ctx.channel
        msg.channel = channel
        msg.author = channel.guild.get_member(who.id) or who
        msg.content = ctx.prefix + command
        new_ctx = await self.sonata.get_context(msg, cls=type(ctx))
        await self.sonata.invoke(new_ctx)

    @core.command()
    async def repeat(self, ctx, times: int, *, command: str):
        _("""Repeats the command the specified number of times""")
        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.sonata.get_context(msg, cls=type(ctx))
        async with ctx.typing():
            for i in range(times):
                await new_ctx.reinvoke()

    async def cog_command_error(self, ctx: core.Context, error):
        original = error.original
        if isinstance(original, commands.ExtensionNotFound):
            await ctx.send(_("I did not find the cog: **{0}**!").format(original.name))
        elif isinstance(original, commands.ExtensionAlreadyLoaded):
            await ctx.send(
                _("The cog is already loaded: **{0}**!").format(original.name)
            )
        elif isinstance(original, commands.ExtensionNotLoaded):
            await ctx.send(_("I did not load the cog: **{0}**!").format(original.name))
        elif isinstance(original, commands.NoEntryPointError):
            await ctx.send(
                _("There is no setup function in the **{0}** extension.").format(
                    original.name
                )
            )
        elif isinstance(original, commands.ExtensionFailed):
            await ctx.send(
                _(
                    "An error occurred in the **{0.name}** cog or its setup function:\n{0.original}"
                ).format(original)
            )
        else:
            await ctx.bot.on_command_error(ctx, error)

    @core.command()
    async def ping(self, ctx: core.Context):
        """Pong!"""
        typings = time.monotonic()
        await ctx.trigger_typing()
        typing = round((time.monotonic() - typings) * 1000)
        latency = round(ctx.bot.latency * 1000)
        discords = time.monotonic()
        url = "https://discord.com/"
        async with ctx.session.get(url) as resp:
            if resp.status == 200:
                _discord = round((time.monotonic() - discords) * 1000)
            else:
                _discord = "Failed"
        await ctx.inform(
            f"Typing: `{typing}ms`\nLatency: `{latency}ms`\nDiscord: `{_discord}ms`",
            title="Pong!",
        )

    @core.group()
    async def cogs(self, ctx: core.Context):
        _("""Lists loaded cogs""")
        if ctx.invoked_subcommand is not None:
            return

        loaded_cogs = list(self.sonata.cogs.keys())
        if not loaded_cogs:
            await ctx.send(_("No loaded cogs!"))
            return

        content = "```"
        if loaded_cogs:
            content += _("Loaded cogs:\n{0}\n").format(", ".join(loaded_cogs))
        content += "```"
        await ctx.send(content)

    @cogs.command()
    async def load(self, ctx: core.Context, cog_name: to_lower):
        _("""Loads cog""")
        await self.sonata.change_presence(status=discord.Status.idle)
        load_extension(self.sonata, cog_name)
        await ctx.send(_("I loaded the cog: **{}**.").format(cog_name.capitalize()))
        await self.sonata.change_presence(status=discord.Status.dnd)

    @cogs.command()
    async def unload(self, ctx: core.Context, cog_name: to_lower):
        _("""Disables cog""")
        if cog_name == to_lower(self.qualified_name):
            await ctx.send(_("This cog cannot be disabled"))
            return

        unload_extension(self.sonata, cog_name)
        await ctx.send(_("I disabled the cog: **{0}**.").format(cog_name.capitalize()))

    @cogs.command()
    async def reload(self, ctx: core.Context, cog_name: to_lower):
        _("""Reloads cog""")
        await self.sonata.change_presence(status=discord.Status.idle)
        reload_extension(self.sonata, cog_name)
        await ctx.send(_("I reloaded the cog: **{0}**.").format(cog_name.capitalize()))
        await self.sonata.change_presence(status=discord.Status.dnd)

    @core.command()
    async def uptime(self, ctx: core.Context):
        _("""Displays uptime""")
        await ctx.send(self.sonata.uptime)

    @core.command(name="eval")
    async def eval_fn(self, ctx: core.Context, *, cmd: EvalExpression()):
        _(
            """Evaluates input
        Input is interpreted as newline separated statements.\
        If the last statement is an expression, that is the return value.\
        Usable globals:
          - `bot`: the bot instance
          - `discord`: the discord module
          - `commands`: the discord.ext.commands module
          - `ctx`: the invocation context
          - `__import__`: the builtin `__import__` function
          - `_`: last result
        Such that `>eval 1 + 1` gives `2` as the result.\
        The following invocation will cause the bot to send the text '9' \
        to the channel of invocation and return '3' as the result of evaluating.
        >>> eval ```py
        a = 1 + 2
        b = a * 2
        await ctx.send(a + b)
        a
        ```
        """
        )
        env = {
            "bot": ctx.bot,
            "discord": discord,
            "commands": commands,
            "ctx": ctx,
            "__import__": __import__,
            "_": self._last_result,
        }
        async with ctx.typing():
            exec(compile(cmd.parsed, filename="<ast>", mode="exec"), env)
            try:
                result = await eval(f"{cmd.fn_name}()", env)
            except Exception as e:
                await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")
            else:
                self._last_result = result
                await ctx.send(f"```py\n{result}\n```")

    @core.command()
    async def source(self, ctx: core.Context, *, command: str = None):
        _(
            """Displays full source code for a specific command
        
        To display the source code of a subcommand you can separate it by \
        periods, e.g. `tag.create` for the create subcommand of the tag command \
        or by spaces.
        """
        )
        source_url = "https://github.com/Fozar/Sonata"
        branch = "master"
        if command is None:
            return await ctx.send(source_url)

        if command == "help":
            src = type(self.sonata.help_command)
            module = src.__module__
            filename = inspect.getsourcefile(src)
        else:
            obj = self.sonata.get_command(command.replace(".", " "))
            if obj is None:
                return await ctx.inform(_("Could not find command."))

            # since we found the command we're looking for, presumably anyway, let's
            # try to access the code itself
            src = obj.callback.__code__
            module = obj.callback.__module__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        if not module.startswith("discord"):
            # not a built-in command
            location = os.path.relpath(filename).replace("\\", "/")
        else:
            location = module.replace(".", "/") + ".py"
            source_url = "https://github.com/Rapptz/discord.py"
            branch = "master"

        final_url = f"<{source_url}/blob/{branch}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>"
        await ctx.inform(final_url)

    @core.command()
    async def sys(self, ctx: core.Context):
        _("""Displays system info""")
        embed = discord.Embed(title=_("System Info"), colour=self.colour)
        embed.add_field(
            name=_("Platform"),
            value=_(
                "**System**: {system}\n**Release**: {release}\n**Uptime**: {uptime}"
            ).format(
                system=platform.system(),
                release=platform.release(),
                uptime=format_timedelta(
                    timedelta(seconds=time.time() - psutil.boot_time()),
                    locale=ctx.locale,
                ),
            ),
        )
        embed.add_field(
            name=_("CPU"),
            value=_("**Cores**: {count}\n**Usage**: {usage}%").format(
                count=psutil.cpu_count(), usage=psutil.cpu_percent()
            ),
        )
        ram = psutil.virtual_memory()
        embed.add_field(
            name=_("RAM"),
            value=_(
                "**Total**: {total}GB\n**Available**: {available}GB\n**Usage**: {usage}%"
            ).format(
                total=round(ram.total / 1024 ** 3, 2),
                available=round(ram.available / 1024 ** 3, 2),
                usage=ram.percent,
            ),
        )
        bot_pid = os.getpid()
        bot = psutil.Process(bot_pid)
        mongo_info = await ctx.db.command("serverStatus")
        mongo = psutil.Process(mongo_info["pid"])
        bot_cpu_percent = partial(bot.cpu_percent, 1.0)
        mongo_cpu_percent = partial(mongo.cpu_percent, 1.0)
        async with ctx.typing():
            bot_cpu, mongo_cpu = tuple(
                await asyncio.gather(
                    ctx.bot.loop.run_in_executor(ctx.pool, bot_cpu_percent),
                    ctx.bot.loop.run_in_executor(ctx.pool, mongo_cpu_percent),
                    loop=ctx.bot.loop,
                )
            )
        embed.add_field(
            name=_("Bot"),
            value=_(
                "**Uptime**: {uptime}\n**PID**: {pid}\n"
                "**Memory usage**: {mem}MB ({mem_percent}%)"
                "\n**CPU usage**: {cpu}%"
            ).format(
                uptime=format_timedelta(
                    timedelta(seconds=time.time() - bot.create_time()),
                    locale=ctx.locale,
                ),
                pid=bot_pid,
                mem=round(bot.memory_info().rss / 1024 ** 2, 2),
                mem_percent=round(bot.memory_percent(), 2),
                cpu=bot_cpu,
            ),
        )

        embed.add_field(
            name=_("Database"),
            value=_(
                "**Uptime**: {uptime}\n**PID**: {pid}\n"
                "**Memory usage**: {mem}MB ({mem_percent}%)"
                "\n**CPU usage**: {cpu}%"
            ).format(
                uptime=format_timedelta(
                    timedelta(seconds=mongo_info["uptime"]), locale=ctx.locale
                ),
                pid=mongo_info["pid"],
                mem=round(mongo.memory_info().rss / 1024 ** 2, 2),
                mem_percent=round(mongo.memory_percent(), 2),
                cpu=mongo_cpu,
            ),
        )
        await ctx.send(embed=embed)

    @core.command()
    async def sh(self, ctx: core.Context, *, command: str):
        _("""Runs a shell command""")
        async with ctx.typing():
            stdout, stderr = await self.run_process(command)

        if stderr:
            text = f"\nstderr:\n```autohotkey\n{stderr}```"
            if stdout:
                text = f"stdout:\n```autohotkey\n{stdout}```\n" + text
        elif stdout:
            text = f"```autohotkey\n{stdout}```"
        else:
            text = "```OK```"

        await ctx.send(text)
