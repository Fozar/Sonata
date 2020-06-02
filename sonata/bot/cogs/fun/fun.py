import random
import re
from contextlib import suppress

import discord
from discord.ext import commands

from sonata.bot import core
from .games import Games
from sonata.bot.utils.converters import to_lower


class DogAPI:
    base_url = "https://dog.ceo/api"
    breeds_list_endpoint = "/breeds/list"
    random_all_breeds_endpoint = "/breeds/image/random"
    random_breed_endpoint = "/breed/{0}/images/random"

    def __init__(self, session):
        self.session = session

    async def _api_request(self, endpoint):
        async with self.session.get(self.base_url + endpoint) as response:
            return await response.json()

    async def list(self):
        return await self._api_request(self.breeds_list_endpoint)

    async def random(self, breed=None):
        if breed is None:
            return await self._api_request(self.random_all_breeds_endpoint)

        return await self._api_request(self.random_breed_endpoint.format(breed))


class Fun(
    Games,
    description=_(
        "A large set of entertainment commands. Everything from 8ball and D&D roll to "
        "cat and dog pictures."
    ),
    colour=discord.Colour.dark_gold(),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        super().__init__()

    @core.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.id == 438476530302189579
            and "ильяс" in message.content.lower()
            and "флуд" in message.content.lower()
        ):
            await message.add_reaction(self.sonata.emoji("Jebaited"))

    def random_magic_ball_response(self) -> str:
        responses = [
            _("definitely."),
            _("yes."),
            _("no."),
            _("of course."),
            _("not really."),
            _("do not be this."),
            _("99% that no."),
            _("no, no, and again no (that's for sure)."),
            _("yes, but later."),
            _("may be."),
            _("in no case."),
            _("who knows?"),
            _("definitely yes."),
            _("are you kidding? ") + str(self.sonata.emoji("kekw")),
            _("I'm tired."),
            _("I have a headache, ask better tomorrow."),
            _("I do not know."),
            _("no, probably."),
            _("stars say yes."),
            _("yes! (no) ") + str(self.sonata.emoji("Kappa")),
            _("what else can you tell?"),
            _("I dont have time for this."),
            _("concentrate and ask again."),
            _("whatever."),
            _("I should know that!?"),
            _("no longer makes sense."),
            _("I won’t even answer."),
            _("yes, congratulations!"),
            _("you should not know it."),
        ]
        return random.choice(responses)

    @core.command(aliases=["8ball", "q"], examples=_("donate to the developer?"))
    async def question(self, ctx: core.Context):
        _("""Answers the question""")
        await ctx.send(f"{ctx.author.mention}, {self.random_magic_ball_response()}")

    @core.command()
    async def coin(self, ctx: core.Context):
        _("""Throws a coin""")
        sides = [_("eagle"), _("tails")]
        await ctx.send(
            f"{ctx.author.mention}, {random.choice(sides)} "
            + str(self.sonata.emoji("coin"))
        )

    @core.command(examples=[_("coffee tea juice"), _("love \"doesn't love\"")])
    async def choose(self, ctx: core.Context, *options: commands.clean_content()):
        _("""Selects one of the options""")
        choice = random.choice(options)
        await ctx.send(f"{ctx.author.mention}, {choice.strip()}")

    @core.command(
        examples=[
            _("5 - rolls 5 dice with 6 faces"),
            _("d54 - rolls 1 dice with 54 faces"),
            _("2d8 - rolls 2 dice with 8 faces"),
            _(
                "+10 + 2d10 - rolls 1 dice with 6 faces and adds 10 to the result, then "
                "rolls 2 dice with 10 faces and adds to the result."
            ),
        ]
    )
    async def roll(self, ctx: core.Context, *, expression: str = ""):
        _(
            """Rolls the dice

        Template: 1d6+0 + 1d6+0 + ..."""
        )  # TODO: Объяснить принцип в описании
        exps = expression.split(" + ")
        result = 0
        for exp in exps:
            match = re.match(
                r"^(?P<count>[1-9]\d*)?(?:d(?P<size>[1-9]\d*))?(?:\+(?P<offset>\d*))?$",
                exp,
            )
            if match is None:
                await ctx.send(_("Invalid expression format."))
                return
            count, size, offset = match.groups()

            count = 1 if count is None else int(count)
            size = 6 if size is None else int(size)
            offset = 0 if offset is None else int(offset)

            if count > 100000:
                count = 100000
            if size > 100000:
                size = 100000
            if offset > 100000:
                offset = 100000

            while count > 0:
                result += random.randint(1, size)
                count -= 1

            result += offset

        await ctx.send(f"{ctx.author.mention}, {result}")

    @core.command()
    async def cat(self, ctx: core.Context):
        _("""Finds a random cat image""")
        async with ctx.session.get(
            "https://api.thecatapi.com/v1/images/search",
            headers={"x-api-key": self.sonata.config["api"].cat_api},
        ) as resp:
            if resp.status != 200:
                return await ctx.send(
                    _("No cat found ") + self.sonata.emoji("BibleThump")
                )
            js = await resp.json()
        await ctx.send(
            embed=discord.Embed(colour=self.colour).set_image(url=js[0]["url"])
        )

    @core.command(examples=["akita"])
    async def dog(self, ctx: core.Context, breed: to_lower = None):
        _(
            """Finds a random dog image
        
        You can also specify the breed of the dog.
        """
        )
        dog_api = DogAPI(ctx.session)
        data = await dog_api.random(breed)
        if breed and data.get("code") == 404:
            data = await dog_api.list()
            message = ", ".join(data.get("message"))
            return await ctx.inform(f"```{message}```", title=_("Breed list"))

        embed = discord.Embed(colour=self.colour)
        embed.set_image(url=data.get("message"))
        await ctx.send(embed=embed)

    @core.command(examples=[_("@Member")])
    @commands.guild_only()
    async def choke(self, ctx: core.Context, member: discord.Member):
        _("""Choke a guild member""")
        await ctx.send(
            _("*{author} chokes {target}* ").format(
                author=ctx.author.display_name, target=member.mention
            )
            + str(self.sonata.emoji("choke"))
        )
        with suppress(discord.HTTPException):
            await ctx.message.delete()

    @core.command(examples=[_("@Member")])
    @commands.guild_only()
    async def hug(self, ctx: core.Context, member: discord.Member):
        _("""Hug a guild member""")
        await ctx.send(
            _("*{author} hugs {target}* ").format(
                author=ctx.author.display_name, target=member.mention
            )
            + str(self.sonata.emoji("GivePLZ"))
        )
        with suppress(discord.HTTPException):
            await ctx.message.delete()

    @core.command(examples=[_("@Member")])
    @commands.guild_only()
    async def hit(self, ctx: core.Context, member: discord.Member):
        _("""Hit a guild member""")
        await ctx.send(
            _("*{author} hits {target}* ").format(
                author=ctx.author.display_name, target=member.mention
            )
            + str(self.sonata.emoji("peepoSmash"))
        )
        with suppress(discord.HTTPException):
            await ctx.message.delete()

    @core.command(examples=[_("@Member")])
    @commands.guild_only()
    async def kiss(self, ctx: core.Context, member: discord.Member):
        _("""Kiss a guild member""")
        await ctx.send(
            _("*{author} kisses {target}* ").format(
                author=ctx.author.display_name, target=member.mention
            )
            + "😘"
        )
        with suppress(discord.HTTPException):
            await ctx.message.delete()

    @core.command(examples=[_("reflects on the eternal")])
    @commands.guild_only()
    async def me(self, ctx: core.Context, *, action):
        _("""Perform a 3rd person action""")
        await ctx.send(f"*{ctx.author.display_name} {action}*")
        with suppress(discord.HTTPException):
            await ctx.message.delete()

    @core.command(examples=[_("@Member")])
    @commands.guild_only()
    async def wink(self, ctx: core.Context, member: discord.Member):
        _("""Wink at guild member""")
        await ctx.send(
            _("*{author} winks at {target}* ").format(
                author=ctx.author.display_name, target=member.mention
            )
            + str(self.sonata.emoji("peepoWink"))
        )
        with suppress(discord.HTTPException):
            await ctx.message.delete()
