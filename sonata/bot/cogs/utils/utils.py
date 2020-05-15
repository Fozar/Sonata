import csv
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

import discord
from babel.dates import format_datetime
from dateutil import parser
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils.converters import MathExpression, to_lower, locale_to_lang
from sonata.bot.utils.paginator import CloseMenu

WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
OW_ICON_URL = "https://openweathermap.org/themes/openweathermap/assets/vendor/owm/img/icons/logo_60x60.png"


class Utils(core.Cog, colour=discord.Colour(0x7ED321)):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    def make_weather_embed(self, weather_response) -> discord.Embed:
        """ Weather embed template """
        weather = weather_response["weather"][0]
        weather_desc = weather["description"].capitalize()
        now = datetime.utcnow()
        local_time = format_datetime(
            now + timedelta(seconds=weather_response["timezone"]),
            locale=self.sonata.locale,
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

    @core.command()
    async def avatar(
        self, ctx: core.Context, member: Optional[discord.Member] = None,
    ):
        _("""Displays a member’s avatar in full size""")
        if member is None:
            member = ctx.author
        embed = discord.Embed(
            title=_("{0} avatar").format(member.display_name), colour=self.colour
        )
        embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    @core.command(aliases=["calc"])
    async def calculate(
        self, ctx: core.Context, *, expression: MathExpression() = None
    ):
        _(
            """Calculates an expression
        
        Supported operations
        ```
        Add (a+b)
        Subtract (a-b)
        Multiply (a*b)
        Divide (a/b)
        Power (a**b or a^b)
        Unary plus (+a)
        Unary minus (-a)
        ```
        
        There is a restriction on the power operation. \
        None of the operands should be greater than 100.
        
        Examples
        ```
        2^6 = 64
        2**6 = 64
        8*8 = 64
        -(4 * (2^2 + 4) + 32) = -64
        ```
        
        """
        )
        await ctx.inform(_("Result: {0}").format(expression.normalize()))

    @core.command(aliases=["virus"])
    async def covid(self, ctx: core.Context, *, country: to_lower = None):
        _("""Shows COVID-19 pandemic statistics""")
        async with ctx.session.get(
            "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/web-data/data/cases_country.csv"
        ) as response:
            csv_file = (await response.content.read()).decode("utf-8")
        data = list(csv.DictReader(StringIO(csv_file), skipinitialspace=True))
        embed = discord.Embed(title="COVID-19", colour=self.colour)
        embed.set_footer(text="Johns Hopkins CSSE")
        embed.set_thumbnail(
            url="https://www.engagespark.com/wp-content/uploads/2019/03/JHU-carousel-logo.png"
        )
        if country and country != _("world"):
            row = next(
                (row for row in data if row["Country_Region"].lower() == country), None
            )
            if row is None:
                return await ctx.inform(_("Country not found."))
            confirmed, deaths, recovered, last_update = (
                int(float(row.get("Confirmed"))),
                int(float(row.get("Deaths"))),
                int(float(row.get("Recovered"))),
                parser.parse(row.get("Last_Update")),
            )
            embed.title += f" - {row.get('Country_Region')}"
        else:
            confirmed, deaths, recovered = (0, 0, 0)
            last_update = None
            for row in data:
                for key, value in row.items():
                    if key == "Confirmed":
                        confirmed += int(float(value))
                    elif key == "Deaths":
                        deaths += int(float(value))
                    elif key == "Last_Update":
                        value = parser.parse(value)
                        if last_update is None or value > last_update:
                            last_update = value
                    elif key == "Recovered":
                        recovered += int(float(value))
            embed.title += _(" - World")
        closed = deaths + recovered
        active = confirmed - closed
        mortality = round(deaths / closed * 100, 2)
        embed.timestamp = last_update
        embed.add_field(name=_("Confirmed cases"), value=str(confirmed))
        embed.add_field(name=_("Active cases"), value=str(active))
        embed.add_field(name=_("Closed cases"), value=str(closed))
        embed.add_field(name=_("Recovered"), value=str(recovered))
        embed.add_field(name=_("Deaths"), value=str(deaths))
        embed.add_field(name=_("Deaths/Closed cases"), value=f"{mortality}%")

        message = await ctx.send(embed=embed)
        await message.add_reaction(self.sonata.emoji("monkaSoap"))

    @core.command(aliases=["w"])
    @commands.cooldown(1, 1)
    async def weather(self, ctx: core.Context, locality: str):
        _(
            """Finds out the weather

        The name of the locality may be specified in any language."""
        )
        params = {
            "q": locality,
            "type": "like",
            "units": "metric",
            "lang": locale_to_lang(ctx.locale),
            "APPID": self.sonata.config["api"].open_weather,
        }
        async with ctx.session.get(WEATHER_URL, params=params) as resp:
            if resp.status != 200:
                return await ctx.send(
                    _("{0}, I did not find such a locality.").format(ctx.author.mention)
                )
            js = await resp.json()
        embed = self.make_weather_embed(js)
        menu = CloseMenu(embed=embed)
        await menu.prompt(ctx)
