from typing import Union

import discord
from babel.dates import format_datetime, format_timedelta
from discord.ext.commands import clean_content

from sonata.bot import core, Sonata
from sonata.bot.utils.misc import make_locale_list

SONATA_INVITE = "https://discordapp.com/api/oauth2/authorize?client_id=355591424319946753&permissions=8&scope=bot"


class General(
    core.Cog, description=_("General commands"), colour=discord.Colour(0x4A90E2)
):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata

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
            await ctx.inform(
                _(
                    "This command allows you to fill in the `About` field, "
                    "which will be displayed in the user profile. Current value:\n`{0}`"
                ).format(about)
            )
            return await ctx.send_help()

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
            url=SONATA_INVITE,
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
        owner = self.sonata.get_user(self.sonata.owner_id)
        inline_fields = {
            _("Name"): f"{self.sonata.emoji('sonata')} {self.sonata.user}",
            _(
                "API wrapper"
            ): "[Discord.py v.1.3.3](https://discordpy.readthedocs.io/en/latest/)",
            _("Developer"): f"{self.sonata.emoji('fozar')} {owner}",
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
                members=len(self.sonata.users),
            ),
            _("Language support"): ", ".join(make_locale_list(display_name=True)),
            _("Useful links"): _("[Invite the bot to your server]({0})").format(
                SONATA_INVITE
            ),
        }
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @core.command(aliases=["user"])
    async def profile(
        self, ctx: core.Context, user: Union[discord.Member, discord.User] = None
    ):
        if user is None:
            user = ctx.author
        embed = discord.Embed(
            title=_("{0} Info").format(user.display_name), colour=self.colour
        )
        embed.set_footer(text=f"ID: {user.id}")
        embed.set_thumbnail(url=user.avatar_url)
        main_info = {_("Name"): str(user)}
        if ctx.guild:
            member = ctx.guild.get_member(user.id)
            if member:
                status_map = {
                    discord.Status.online: _("Online"),
                    discord.Status.offline: _("Offline"),
                    discord.Status.idle: _("Idle"),
                    discord.Status.do_not_disturb: _("Do Not Disturb"),
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
            user.created_at, locale=ctx.locale
        )
        main_info = [f"**{key}**: {value}" for key, value in main_info.items()]
        embed.add_field(name=_("Summary"), value="\n".join(main_info), inline=False)
        if user.bot:
            return await ctx.send(embed=embed)
        user_conf = await ctx.db.users.find_one(
            {"id": user.id},
            {
                "about": True,
                "created_at": True,
                "total_messages": True,
                "commands_invoked": True,
                "lvl": True,
                "exp": True,
            },
        )
        global_rank = await ctx.db.users.count_documents(
            {"exp": {"$gte": user_conf["exp"]}}
        )

        if "about" in user_conf:
            embed.description = user_conf["about"]
        stats_cog = self.sonata.cogs.get("Stats")
        statistics = {
            _("Statistics has been running since"): format_datetime(
                user_conf["created_at"], locale=ctx.locale
            ),
            _("Total messages"): user_conf["total_messages"],
            _("Commands invoked"): user_conf["commands_invoked"],
            _("Level"): user_conf["lvl"],
            _(
                "Experience"
            ): f"{user_conf['exp']}/{stats_cog.calculate_exp(user_conf['lvl'] + 1)}",
            _("Global rank"): global_rank,
        }
        if ctx.guild and ctx.guild.get_member(user.id):
            guild_conf = await ctx.db.guilds.find_one(
                {"id": ctx.guild.id}, {"leveling": True}
            )
            if guild_conf["leveling"]:
                statistics[_("Guild rank")] = await ctx.db.users.count_documents(
                    {"guilds": ctx.guild.id, "exp": {"$gte": user_conf["exp"]}}
                )
        statistics = [f"**{key}**: {value}" for key, value in statistics.items()]
        statistics = "\n".join(statistics)
        statistics += _("\n`Statistics counts only messages visible to the bot`")
        embed.add_field(name=_("Statistics"), value=statistics, inline=False)

        await ctx.send(embed=embed)
