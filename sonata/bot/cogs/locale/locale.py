import copy

import discord
from babel import Locale as BabelLocale
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils import i18n
from sonata.bot.utils.converters import validate_locale, locale_to_flag
from sonata.bot.utils.misc import make_locale_list


def admin_or_dm(ctx: core.Context):
    if ctx.guild is not None and not ctx.author.guild_permissions.administrator:
        raise commands.PrivateMessageOnly()

    return True


class Locale(
    core.Cog,
    description=_(
        "This module allows you to set the language in direct messages and display a "
        "list of supported languages."
    ),
    colour=discord.Colour.light_grey(),
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @core.command(examples=["en_US"])
    @commands.check(admin_or_dm)
    async def locale(self, ctx: core.Context, locale: validate_locale = None):
        _("""Set locale""")
        if ctx.guild:
            msg = copy.copy(ctx.message)
            msg.content = ctx.prefix + f"guild locale {locale}"
            new_ctx = await self.sonata.get_context(msg, cls=type(ctx))
            return await ctx.bot.invoke(new_ctx)
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
        await self.sonata.cache.delete(f"locale_{ctx.author.id}")
        await ctx.inform(
            _("The user locale is set to {flag} `{locale}`.").format(
                flag=locale_to_flag(locale), locale=locale
            )
        )

    @core.group()
    async def locales(self, ctx: core.Context):
        _("""Returns a list of supported locales""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.inform(
            _("Available locales: {0}.").format(", ".join(make_locale_list()))
        )

    @locales.command(name="update", hidden=True)
    @commands.is_owner()
    async def locales_update(self, ctx: core.Context):
        i18n.update_translations()
        await ctx.inform(_("Locales updated"))
