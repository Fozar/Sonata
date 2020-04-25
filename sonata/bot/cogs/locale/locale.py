import discord
from babel import Locale as BabelLocale
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils import i18n
from sonata.bot.utils.converters import validate_locale, locale_to_flag
from sonata.bot.utils.misc import make_locale_list


class Locale(
    core.Cog, description=_("""Multilingual support"""), colour=discord.Colour(0xFFFFFE)
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.command()
    @commands.dm_only()
    async def locale(self, ctx: core.Context, locale: validate_locale = None):
        _("""Set user locale""")
        if locale is None:
            user = await ctx.db.users.find_one({"id": ctx.author.id}, {"locale": True})
            return await ctx.inform(
                _("Current user locale is {flag} `{locale}`.").format(
                    flag=locale_to_flag(user["locale"]),
                    locale=BabelLocale.parse(user["locale"], sep="_").display_name,
                )
            )

        await ctx.db.users.update_one(
            {"id": ctx.author.id}, {"$set": {"locale": locale}}
        )
        ctx.locale = locale
        await ctx.inform(
            _("The user locale is set to {flag} `{locale}`.").format(
                flag=locale_to_flag(locale), locale=locale
            )
        )

    @core.command()
    async def locales(self, ctx: core.Context):
        _("""Returns a list of supported locales""")
        await ctx.inform(
            _("Available locales: {0}.").format(", ".join(make_locale_list()))
        )
