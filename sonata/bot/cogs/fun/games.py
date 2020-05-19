import asyncio
import random

import discord

from sonata.bot import core


class Games(core.Cog):
    def __init__(self):
        self.sessions = []

    @staticmethod
    def make_number():
        numbers = list(map(str, range(1, 10)))
        random.shuffle(numbers)
        number = numbers.pop(0)
        numbers.append("0")
        for i in range(3):
            random.shuffle(numbers)
            number += numbers.pop(i)
        return number

    @staticmethod
    def check_number(number: str, guess: str):
        bulls = cows = 0
        for i in range(4):
            if guess[i] in number:
                if guess[i] == number[i]:
                    bulls += 1
                else:
                    cows += 1
        return {"bulls": bulls, "cows": cows}

    @core.group()
    async def game(self, ctx: core.Context):
        _("""Starts a game session""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()

    @game.command(name="B&C")
    async def bulls_and_cows(self, ctx: core.Context):
        _(
            """Bulls & Cows
        
        I will make a secret 4-digit number with non-repeating numbers, and you will \
        make attempts to guess it. An attempt is a 4-digit number with non-repeating \
        numbers. Each attempt is given 60 seconds. I will inform you in response to how \
        many numbers were guessed without coincidence with their positions in the secret\
         number (i.e. the number of cows) and how many were guessed right up to the \
        position in the secret number (i.e. the number of bulls).
        
        Example:
            Concealed secret number "3219".
            Attempt: "2310".
            Result: two "cows" (two digits: "2" and "3" - guessed at the wrong positions) \
        and one “bull” (one digit "1" guessed right up to the position).
        """
        )
        if ctx.author.id in self.sessions:
            return await ctx.inform(_("You cannot start more than one game session."))

        self.sessions.append(ctx.author.id)
        number = self.make_number()
        await ctx.inform(
            _(
                "I made a secret 4-digit number with non-repeating numbers. Try to guess!"
                " You have 60 seconds for every attempt."
            )
        )

        async def check_input(attempt):
            try:
                int(attempt)
            except ValueError:
                msg = await ctx.inform(_("The attempt must be a number."))
            else:
                if len(attempt) != 4:
                    msg = await ctx.inform(_("The number must be 4 digits."))
                elif attempt.startswith("0"):
                    msg = await ctx.inform(_("A number cannot start from zero."))
                elif len(set(attempt)) < len(attempt):
                    msg = await ctx.inform(
                        _("The number should not be duplicate numbers.")
                    )
                else:
                    return True
            await msg.delete(delay=5.0)
            return False

        embed = discord.Embed(title=_("Bulls & Cows"), colour=self.colour)
        attempts_total = 0
        attempts = []
        embed.add_field(name=_("🐂 Bulls"), value="0")
        embed.add_field(name=_("🐄 Cows"), value="0")
        embed.set_footer(text=_("Total attempts: {0}").format(attempts_total))
        stats = await ctx.send(embed=embed)
        while True:
            try:
                msg = await ctx.bot.wait_for(
                    "message",
                    check=lambda msg: msg.channel == ctx.channel
                    and msg.author == ctx.author,
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                await ctx.inform(_("Time is over!"))
                break
            else:
                try:
                    await msg.delete(delay=5.0)
                except discord.Forbidden:
                    pass
            attempt = msg.content
            if not await check_input(attempt):
                continue

            attempts_total += 1
            attempts.append(f"`{attempt}`")
            if len(attempts) > 10:
                attempts.pop(0)
            check = self.check_number(number, attempt)
            embed.clear_fields()
            embed.add_field(
                name=_("Last attempts"), value=" ".join(attempts[::-1]), inline=False
            )
            embed.add_field(name=_("🐂 Bulls"), value=str(check["bulls"]))
            embed.add_field(name=_("🐄 Cows"), value=str(check["cows"]))
            embed.set_footer(text=_("Total attempts: {0}").format(attempts_total))

            won = False
            if check["bulls"] == 4:
                response = _("Victory!")
                won = True
            elif check["bulls"] == 3:
                response = _("A little bit more..")
            elif check["bulls"] == 2:
                response = _("You are already close!")
            elif check["bulls"] == 1:
                response = _("The right direction.")
            elif check["cows"] > 0:
                response = _("The tactics are correct.")
            else:
                response = _("Trying is not torture. Try once more.")

            embed.description = f"*{response}*"

            await stats.edit(embed=embed)
            if won:
                break
        self.sessions.remove(ctx.author.id)
