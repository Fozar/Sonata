import discord
from babel import Locale as BabelLocale
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils import i18n


class Locale(
    core.Cog, description=_("""Multilingual support"""), colour=discord.Colour(0xFFFFFF)
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def define_locale(self, msg: discord.Message):
        if msg.guild:
            guild = await self.sonata.db.guilds.find_one(
                {"id": msg.guild.id},
                {
                    "locale": True,
                    "premium": True,
                    "channels": {"$elemMatch": {"id": msg.channel.id}},
                },
            )
            if guild["premium"] and "channels" in guild:
                return guild["channels"][0]["locale"]

            return guild["locale"]
        else:
            user = await self.sonata.db.users.find_one(
                {"id": msg.author.id}, {"locale": True}
            )
            return user["locale"]

    @core.command()
    @commands.dm_only()
    async def locale(self, ctx: core.Context, locale: str = None):
        _("""Set user locale""")
        if locale is None:
            user = await ctx.db.users.find_one({"id": ctx.author.id}, {"locale": True})
            return await ctx.inform(
                _("Current user locale is {flag} `{locale}`.").format(
                    flag=i18n.locale_to_flag(user["locale"]),
                    locale=BabelLocale.parse(user["locale"], sep="_").display_name,
                )
            )

        if locale not in i18n.gettext_translations.keys():
            return await ctx.inform(
                _("Locale not found. Available locales: {0}.").format(
                    ", ".join(i18n.make_locale_list())
                )
            )

        await ctx.db.users.update_one(
            {"id": ctx.author.id}, {"$set": {"locale": locale}}
        )
        i18n.current_locale.set(locale)
        await ctx.inform(
            _("The user locale is set to {flag} `{locale}`.").format(
                flag=i18n.locale_to_flag(locale), locale=locale
            )
        )
