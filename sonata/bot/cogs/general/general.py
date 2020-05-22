from typing import Union

import discord
from babel.dates import format_datetime, format_timedelta
from discord.ext import commands
from discord.ext.commands import clean_content

from sonata.bot import core, Sonata
from sonata.bot.utils.misc import make_locale_list


class General(
    core.Cog,
    description=_("General commands and information."),
    colour=discord.Colour.blue(),
):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata
        self._original_help_command = sonata.help_command
        sonata.help_command = core.HelpCommand()
        sonata.help_command.cog = self

    def cog_unload(self):
        self.sonata.help_command = self._original_help_command

    @core.group(invoke_without_command=True)
    async def about(
        self, ctx: core.Context, *, about: Union[clean_content, str] = None
    ):
        _("""Fills in "About" field in the profile info""")
        if ctx.invoked_subcommand is not None:
            return
        if about is None:
            user_conf = await ctx.db.users.find_one(
                {"id": ctx.author.id}, {"about": True}
            )
            about = user_conf.get("about") or _("The field is not filled.")
            return await ctx.inform(
                _(
                    "This command allows you to fill in the `About` field, "
                    "which will be displayed in the user profile. Current value:\n`{0}`"
                ).format(about)
            )

        if len(about) < 20:
            await ctx.inform(_("The field length cannot be less than 20 characters."))
        elif len(about) > 2000:
            await ctx.inform(
                _("The field length cannot be greater than 2000 characters.")
            )
        else:
            await ctx.db.users.update_one(
                {"id": ctx.author.id}, {"$set": {"about": about}}
            )
            await ctx.inform(_("The `About` field is set."))

    @about.command(name="clear")
    async def about_clear(self, ctx: core.Context):
        _("""Clears "About" field in profile info.""")
        await ctx.db.users.update_one({"id": ctx.author.id}, {"$set": {"about": None}})
        await ctx.inform(_("The `About` field is cleared."))

    @core.command()
    async def invite(self, ctx: core.context):
        _("""Returns an invitation link""")
        embed = discord.Embed(
            title=_("You can invite me at this link"),
            url=ctx.bot.invite,
            colour=self.colour,
        )
        await ctx.send(embed=embed)

    @core.command(aliases=["bot", "info"])
    async def sonata(self, ctx: core.Context):
        _("""Shows information about me""")
        embed = discord.Embed(
            title=_("Sonata Info"),
            colour=self.colour,
            description=self.sonata.description,
        )
        embed.set_thumbnail(url=self.sonata.user.avatar_url)
        app_info = await self.sonata.application_info()
        inline_fields = {
            _("Name"): f"{self.sonata.emoji('sonata')} {self.sonata.user}",
            _(
                "API wrapper"
            ): f"[discord.py {discord.__version__}](https://discordpy.readthedocs.io/en/latest/)",
            _("Developer"): f"{self.sonata.emoji(704606245495242752)} {app_info.owner}",
        }
        for name, value in inline_fields.items():
            embed.add_field(name=name, value=value)
        fields = {
            _("Status"): _(
                "**Last restart**: {launch_time}\n"
                "**Online**: {online}\n"
                "**Serving**: {guilds} guilds and {members} members."
            ).format(
                launch_time=format_datetime(
                    self.sonata.launch_time, format="long", locale=ctx.locale,
                ),
                online=format_timedelta(self.sonata.uptime, locale=ctx.locale),
                guilds=len(self.sonata.guilds),
                members=sum([guild.member_count for guild in self.sonata.guilds]),
            ),
            _("Language support"): ", ".join(make_locale_list(display_name=True)),
            _("Useful links"): _(
                "[Invite the bot to your server]({invite})\n"
                "[Vote for the bot]({vote})"
            ).format(
                invite=ctx.bot.invite, vote=f"https://top.gg/bot/{ctx.bot.user.id}"
            ),
        }
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @core.command(aliases=["user"])
    @commands.guild_only()
    async def profile(self, ctx: core.Context, member: discord.Member = None):
        if member is None:
            member = ctx.author
        embed = discord.Embed(
            title=_("{0} Info").format(member.display_name), colour=self.colour
        )
        embed.set_footer(text=f"ID: {member.id}")
        embed.set_thumbnail(url=member.avatar_url)
        main_info = {_("Name"): str(member)}

        status_map = {
            discord.Status.online: f"{ctx.bot.emoji('online')} " + _("Online"),
            discord.Status.offline: f"{ctx.bot.emoji('invisible')} " + _("Offline"),
            discord.Status.idle: f"{ctx.bot.emoji('idle')} " + _("Idle"),
            discord.Status.do_not_disturb: f"{ctx.bot.emoji('dnd')} "
            + _("Do Not Disturb"),
        }
        main_info[_("Status")] = status_map.get(member.status)
        if member.activity:
            if member.activity.type == discord.ActivityType.playing:
                main_info[_("Playing")] = member.activity.name
            elif member.activity.type == discord.ActivityType.streaming:
                main_info[_("Streaming")] = member.activity.name
            elif member.activity.type == discord.ActivityType.listening:
                main_info[_("Listening")] = member.activity.title
            elif member.activity.type == discord.ActivityType.custom:
                main_info[_("Activity")] = member.activity.name
                if member.activity.emoji:
                    main_info[
                        _("Activity")
                    ] = f"{member.activity.emoji} {main_info[_('Activity')]}"
        main_info[_("Joined the guild")] = format_datetime(
            member.joined_at, locale=ctx.locale
        )
        main_info[_("Registration date")] = format_datetime(
            member.created_at, locale=ctx.locale
        )
        main_info = [f"**{key}**: {value}" for key, value in main_info.items()]
        embed.add_field(name=_("Summary"), value="\n".join(main_info), inline=False)
        if member.bot:
            return await ctx.send(embed=embed)
        user = await ctx.db.users.find_one({"id": member.id}, {"about": True})
        user_stats = await ctx.db.user_stats.find_one(
            {"guild_id": ctx.guild.id, "user_id": member.id},
            {
                "created_at": True,
                "total_messages": True,
                "commands_invoked": True,
                "lvl": True,
                "exp": True,
            },
        )

        if user.get("about"):
            embed.description = user["about"]
        stats_cog = self.sonata.cogs.get("Stats")
        statistics = {
            _("Statistics has been running since"): format_datetime(
                user_stats["created_at"], locale=ctx.locale
            ),
            _("Total messages"): user_stats["total_messages"],
            _("Commands invoked"): user_stats["commands_invoked"],
            _("Level"): user_stats["lvl"],
            _(
                "Experience"
            ): f"{user_stats['exp']}/{stats_cog.calculate_exp(user_stats['lvl'] + 1)}",
        }
        if ctx.guild and ctx.guild.get_member(member.id):
            statistics[_("Guild rank")] = await ctx.db.user_stats.count_documents(
                {"guild_id": ctx.guild.id, "exp": {"$gte": user_stats["exp"]}}
            )
        statistics = [f"**{key}**: {value}" for key, value in statistics.items()]
        statistics = "\n".join(statistics)
        statistics += _("\n`Statistics counts only messages visible to the bot`")
        embed.add_field(name=_("Statistics"), value=statistics, inline=False)

        await ctx.send(embed=embed)

    @core.command()
    async def report(self, ctx: core.Context, *, report: clean_content()):
        _("""Sends a bug report to the bot owner""")
        embed = discord.Embed(
            colour=self.colour,
            title="Отчет об ошибке",
            description=report,
            timestamp=ctx.message.created_at,
        )
        if ctx.guild:
            embed.add_field(
                name="Гильдия", value=f"{ctx.guild.name} (ID: {ctx.guild.id})"
            )
            embed.add_field(name="Владелец", value=str(ctx.guild.owner))
        embed.add_field(
            name="Канал", value=f"{ctx.channel.name} (ID: {ctx.channel.id})"
        )
        embed.add_field(name="Автор", value=str(ctx.author))
        await ctx.bot.reports_channel.send(embed=embed)
        await ctx.message.add_reaction("✅")

    @core.command()
    @commands.check(lambda ctx: ctx.bot.dbl_client is not None)
    async def widget(self, ctx: core.Context):
        embed = discord.Embed(
            colour=self.colour,
            title=_("Vote for the bot"),
            url=f"https://top.gg/bot/{ctx.bot.user.id}",
        )
        widget = await ctx.bot.dbl_client.generate_widget_large()
        embed.set_image(url=widget)
        await ctx.send(embed=embed)
