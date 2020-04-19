import csv
from datetime import datetime, timedelta
from io import StringIO
from typing import Union

import discord
from babel.dates import format_datetime, format_timedelta
from dateutil import parser
from discord.ext import commands
from discord.ext.commands import UserConverter

from sonata.bot import core, Sonata
from sonata.bot.utils import i18n
from sonata.bot.utils.misc import to_lower
from sonata.bot.utils.paginator import EmbedPaginator
from sonata.config import ApiConfig

api_config = ApiConfig()

WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
OW_ICON_URL = "https://openweathermap.org/themes/openweathermap/assets/vendor/owm/img/icons/logo_60x60.png"
SONATA_INVITE = "https://discordapp.com/api/oauth2/authorize?client_id=355591424319946753&permissions=8&scope=bot"


class General(
    core.Cog, description=_("General commands"), colour=discord.Colour(0x4A90E2)
):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata

    @core.command()
    async def about(self, ctx: core.Context, *, about: str = None):
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

    @core.command()
    async def avatar(
        self,
        ctx: core.Context,
        member: Union[commands.MemberConverter, discord.Member, None] = None,
    ):
        _("""Displays a member’s avatar in full size""")
        if member is None:
            member = ctx.author
        embed = discord.Embed(
            title=_("{0} avatar").format(member.display_name), colour=self.colour
        )
        embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    def make_weather_embed(self, weather_response) -> discord.Embed:
        """ Weather embed template """
        weather = weather_response["weather"][0]
        weather_desc = weather["description"].capitalize()
        now = datetime.utcnow()
        local_time = format_datetime(
            now + timedelta(seconds=weather_response["timezone"]),
            locale=i18n.current_locale.get(),
        )
        embed = discord.Embed(title=weather_desc, colour=self.colour, timestamp=now,)

        weather_icon_url = f"http://openweathermap.org/img/wn/{weather['icon']}@2x.png"
        embed.set_thumbnail(url=weather_icon_url)
        embed.set_author(name=weather_response["name"])
        embed.set_footer(
            text="OpenWeather", icon_url=OW_ICON_URL,
        )

        weather_main = weather_response["main"]
        embed.add_field(
            name=_("Temperature"),
            value=f"{round(weather_main['temp'])} °C",
            inline=True,
        )
        embed.add_field(
            name=_("Feels like"),
            value=f"{round(weather_main['feels_like'])} °C",
            inline=True,
        )
        embed.add_field(
            name=_("Humidity"), value=f"{weather_main['humidity']}%", inline=True
        )
        embed.add_field(
            name=_("Pressure"),
            value=_("{0} mbar").format(weather_main["pressure"]),
            inline=True,
        )
        wind = weather_response["wind"]
        embed.add_field(
            name=_("Wind speed"),
            value=_("{0} m/s").format(round(wind["speed"])),
            inline=True,
        )
        embed.add_field(
            name=_("Local time"), value=local_time, inline=True,
        )
        return embed

    @core.command(aliases=["virus"])
    async def covid(self, ctx: core.Context, *, country: to_lower = None):
        _("""Shows COVID-19 pandemic statistics""")
        async with ctx.session.get(
            "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/web-data/data/cases_country.csv"
        ) as response:
            csv_file = (await response.content.read()).decode("utf-8")
        dict_reader = csv.DictReader(StringIO(csv_file), skipinitialspace=True)
        data = [row for row in dict_reader]
        row = (
            next(
                (row for row in data if row["Country_Region"].lower() == country), None
            )
            if country
            else None
        )
        embed = discord.Embed(title="COVID-19", colour=self.colour)
        embed.set_footer(text="Johns Hopkins CSSE")
        embed.set_thumbnail(
            url="https://www.engagespark.com/wp-content/uploads/2019/03/JHU-carousel-logo.png"
        )
        if row is not None:
            confirmed, deaths, recovered, last_update = (
                int(row.get("Confirmed")),
                int(row.get("Deaths")),
                int(row.get("Recovered")),
                parser.parse(row.get("Last_Update")),
            )
            embed.title += f" - {row.get('Country_Region')}"
        else:
            confirmed, deaths, recovered = (0, 0, 0)
            last_update = None
            for row in data:
                for key, value in row.items():
                    if key == "Confirmed":
                        confirmed += int(value)
                    elif key == "Deaths":
                        deaths += int(value)
                    elif key == "Last_Update":
                        value = parser.parse(value)
                        if last_update is None or value > last_update:
                            last_update = value
                    elif key == "Recovered":
                        recovered += int(value)
            embed.title += _(" - World")
        closed = deaths + recovered
        active = confirmed - closed
        mortality = round(deaths / closed * 100, 2)
        embed.timestamp = last_update
        embed.add_field(name=_("Confirmed cases"), value=str(confirmed), inline=True)
        embed.add_field(name=_("Active cases"), value=str(active), inline=True)
        embed.add_field(name=_("Closed cases"), value=str(closed), inline=True)
        embed.add_field(name=_("Recovered"), value=str(recovered), inline=True)
        embed.add_field(name=_("Deaths"), value=str(deaths), inline=True)
        embed.add_field(
            name=_("Deaths/Closed cases"), value=f"{mortality}%", inline=True
        )

        message = await ctx.send(embed=embed)
        await message.add_reaction(self.sonata.emoji("monkaSoap"))

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
                    self.sonata.launch_time,
                    format="long",
                    locale=i18n.current_locale.get(),
                ),
                online=format_timedelta(
                    self.sonata.uptime, locale=i18n.current_locale.get()
                ),
                guilds=len(self.sonata.guilds),
                members=len(self.sonata.users),
            ),
            _("Language support"): ", ".join(i18n.make_locale_list(display_name=True)),
            _("Useful links"): _("[Invite the bot to your server]({0})").format(
                SONATA_INVITE
            ),
        }
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @core.command()
    async def user(
        self, ctx: core.Context, user: Union[UserConverter, discord.User] = None
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
                    member.joined_at, locale=i18n.current_locale.get()
                )
        main_info[_("Registration date")] = format_datetime(
            user.created_at, locale=i18n.current_locale.get()
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
                user_conf["created_at"], locale=i18n.current_locale.get()
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

    @core.command(aliases=["w"])
    async def weather(self, ctx: core.Context, locality: str):
        _(
            """Finds out the weather

        The name of the locality may be specified in any language."""
        )
        params = {
            "q": locality,
            "type": "like",
            "units": "metric",
            "lang": i18n.current_locale.get()[:2],
            "APPID": api_config.open_weather,
        }
        async with ctx.session.get(WEATHER_URL, params=params) as resp:
            if resp.status != 200:
                return await ctx.send(
                    _("{0}, I did not find such a locality.").format(ctx.author.mention)
                )
            js = await resp.json()
        embed = self.make_weather_embed(js)
        paginator = EmbedPaginator(controls={"❌": EmbedPaginator.close_pages})
        paginator.add_page(embed)
        await paginator.send_pages(ctx)
