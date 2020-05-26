import functools
from typing import Union, List, Dict, TYPE_CHECKING

import discord
from discord.ext import commands

from .command import Command, Group

if TYPE_CHECKING:
    from .context import Context


class _HelpCommandImpl(Command):
    def __init__(self, inject, **kwargs):
        self.on_error = None
        super().__init__(inject.command_callback, **kwargs)
        self._original = inject
        self._injected = inject

    async def prepare(self, ctx):
        self._injected = injected = self._original.copy()
        injected.context = ctx
        self.callback = injected.command_callback

        on_error = injected.on_help_command_error
        if not hasattr(on_error, "__help_command_not_overriden__"):
            if self.cog is not None:
                self.on_error = self._on_error_cog_implementation
            else:
                self.on_error = on_error

        await super().prepare(ctx)

    async def _parse_arguments(self, ctx):
        # Make the parser think we don't have a cog so it doesn't
        # inject the parameter into `ctx.args`.
        original_cog = self.cog
        self.cog = None
        try:
            await super()._parse_arguments(ctx)
        finally:
            self.cog = original_cog

    # noinspection PyUnusedLocal
    async def _on_error_cog_implementation(self, dummy, ctx, error):
        await self._injected.on_help_command_error(ctx, error)

    @property
    def clean_params(self):
        result = self.params.copy()
        try:
            result.popitem(last=False)
        except Exception:
            raise ValueError("Missing context parameter") from None
        else:
            return result

    def _inject_into_cog(self, cog):
        # Warning: hacky

        # Make the cog think that get_commands returns this command
        # as well if we inject it without modifying __cog_commands__
        # since that's used for the injection and ejection of cogs.
        def wrapped_get_commands(*, _original=cog.get_commands):
            ret = _original()
            ret.append(self)
            return ret

        # Ditto here
        def wrapped_walk_commands(*, _original=cog.walk_commands):
            yield from _original()
            yield self

        functools.update_wrapper(wrapped_get_commands, cog.get_commands)
        functools.update_wrapper(wrapped_walk_commands, cog.walk_commands)
        cog.get_commands = wrapped_get_commands
        cog.walk_commands = wrapped_walk_commands
        self.cog = cog

    def _eject_cog(self):
        if self.cog is None:
            return

        # revert back into their original methods
        cog = self.cog
        cog.get_commands = cog.get_commands.__wrapped__
        cog.walk_commands = cog.walk_commands.__wrapped__
        self.cog = None


class HelpCommand(commands.HelpCommand):
    def __init__(self, **options):
        self.dm_help = False
        help_help = _(
            "Help for member commands available.\n\n"
            "Commands for which the member has insufficient rights will not be "
            "displayed. If help is requested for a specific command, detailed "
            "information on its use will be displayed. If the command has "
            "subcommands, they will be listed."
        )
        command_attrs = {
            "brief": _("Shows this message"),
            "aliases": ["h", "commands"],
            "help": help_help,
        }
        super().__init__(command_attrs=command_attrs, **options)

    def _add_to_bot(self, bot):
        command = _HelpCommandImpl(self, **self.command_attrs)
        bot.add_command(command)
        self._command_impl = command

    @property
    def no_category(self):
        return _("No category")

    @property
    def no_desc(self):
        return _("No description")

    def make_footer(self):
        return _("Requested by {0}").format(self.context.author.display_name)

    def command_not_found(self, string: str):
        return _("No command called `{0}` found.").format(string)

    def subcommand_not_found(self, command: Union[Command, Group], string):
        if isinstance(command, Group) and len(command.all_commands) > 0:
            return "Command `{command}` has no subcommand named `{subcommand}`".format(
                command=command.qualified_name, subcommand=string
            )
        return "Command `{0}` has no subcommands.".format(command.qualified_name)

    def make_command_list(self, commands: List[Command]):
        command_list = ""
        for command in commands:
            signature = self.context.prefix + command.qualified_name
            command_help = command.short_doc if command.short_doc else self.no_desc
            command_list += f"`{signature}` {command_help}\n"
        return command_list

    def make_embed(
        self, title: str, description: str = None, fields: Dict[str, str] = None
    ):
        embed = discord.Embed(
            title=title,
            colour=self.cog.colour if self.cog else discord.Colour(0x9B9B9B),
        )
        if description:
            embed.description = description
        if fields:
            for name, value in fields.items():
                if not name or not value:
                    continue
                embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=self.make_footer())
        return embed

    def get_destination(self):
        if self.dm_help:
            return self.context.author
        return self.context.channel

    async def send_bot_help(self, mapping):
        fields = {}
        for cog, commands in mapping.items():
            filtered = await self.filter_commands(commands, sort=True)
            if not filtered:
                continue
            command_names = [command.qualified_name for command in filtered]
            command_list = f"`{'` `'.join(command_names)}`"
            fields[cog.qualified_name if cog else self.no_category] = command_list
        fields = dict(sorted(fields.items()))

        embed = self.make_embed(title=_("Command list"), fields=fields)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        if not filtered:
            return

        commands = self.make_command_list(filtered)
        embed = self.make_embed(
            _("Cog {0}").format(cog.qualified_name),
            cog.description,
            {_("__Commands:__"): commands},
        )
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: Group):
        filtered = await self.filter_commands(group.commands, sort=True)
        subcommands = self.make_command_list(filtered)
        embed = self.make_embed(
            _("Command {0}").format(self.context.prefix + group.qualified_name),
            group.help,
            {
                _("__Usage:__"): f"`{self.get_command_signature(group)}`",
                _("__Subcommands:__"): subcommands,
            },
        )
        await self.context.channel.send(embed=embed)

    async def send_command_help(self, command: Command):
        embed = self.make_embed(
            _("Command {0}").format(self.context.prefix + command.qualified_name),
            command.help,
            {_("__Usage:__"): f"`{self.get_command_signature(command)}`"},
        )
        await self.context.channel.send(embed=embed)

    async def prepare_help_command(self, ctx, command=None):
        if ctx.guild:
            conf = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"dm_help": True})
            self.dm_help = conf["dm_help"]
        else:
            self.dm_help = False

    async def command_callback(self, ctx: "Context", *, command=None):
        await super().command_callback(ctx=ctx, command=command)
        if self.dm_help:
            await ctx.message.add_reaction("✅")
