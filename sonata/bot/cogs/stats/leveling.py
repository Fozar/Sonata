import math
import random
from typing import Dict, Union

import discord
from discord.ext import commands

from sonata.bot import core, Sonata


class Leveling(core.Cog):
    def __init__(self, sonata: Sonata):
        self.sonata = sonata
        self.exp_offset = 100
        self.exp_multiplier = 100

    def calculate_exp(self, lvl: int):
        return (
            math.ceil(self.exp_multiplier * lvl ** 2 - self.exp_multiplier * lvl)
            + self.exp_offset
        )

    async def make_leaderboard_embed(self, user_list: Dict[int, Dict[str, int]]):
        embed = discord.Embed(colour=self.colour)
        for rank, user_conf in user_list.items():
            try:
                user = self.sonata.get_user(
                    user_conf["user_id"]
                ) or await self.sonata.fetch_user(user_conf["user_id"])
            except discord.HTTPException:
                continue
            embed.add_field(
                name=f"`#{rank}` **{user.display_name}**",
                value=_("**Level**: {lvl} | **Experience**: {exp}/{max_exp}").format(
                    lvl=user_conf["lvl"],
                    exp=user_conf["exp"],
                    max_exp=self.calculate_exp(user_conf["lvl"] + 1),
                ),
                inline=False,
            )
        return embed

    def make_lvlup_embed(self, member: discord.Member, lvl: int, exp: int, rank: int):
        embed = discord.Embed(
            colour=self.colour,
            title=_("Level up"),
            description=_("**{user}** has reached level **{lvl}**!").format(
                user=member.display_name, lvl=lvl
            ),
        )
        embed.set_thumbnail(url=member.avatar_url)
        embed.set_footer(
            text=_("Rank: #{rank} | Experience: {exp}/{max_exp}").format(
                rank=rank, exp=exp, max_exp=self.calculate_exp(lvl + 1),
            )
        )
        return embed

    async def lvl_up(self, message, exp, lvl):
        rank = await self.sonata.db.user_stats.count_documents(
            {"guild_id": message.guild.id, "exp": {"$gte": exp}}
        )
        guild = await self.sonata.db.guilds.find_one(
            {"id": message.guild.id}, {"auto_lvl_msg": True}
        )
        if guild["auto_lvl_msg"]:
            user = await self.sonata.db.user_stats.find_one(
                {"guild_id": message.guild.id, "user_id": message.author.id},
                {"auto_lvl_msg": True},
            )
            send_msg = user.get("auto_lvl_msg", True)
        else:
            send_msg = guild["auto_lvl_msg"]

        if send_msg:
            await self.sonata.set_locale(message)
            embed = self.make_lvlup_embed(message.author, lvl, exp, rank)
            await message.channel.send(embed=embed)

    async def update_user_exp(self, message, exp, lvl):
        exp = random.randint(5, 15) * int(1 + lvl / 17) + exp
        update = {
            "$set": {"last_exp_at": message.created_at, "exp": exp},
        }
        next_lvl = lvl + 1
        if exp >= self.calculate_exp(next_lvl):
            lvl = next_lvl
            update["$set"]["lvl"] = lvl
        await self.sonata.db.user_stats.update_one(
            {"guild_id": message.guild.id, "user_id": message.author.id}, update
        )
        if lvl == next_lvl:
            await self.lvl_up(message, exp, lvl)

    @core.group(invoke_without_command=True, examples=[_("@Member"), "15"])
    @commands.guild_only()
    async def rank(
        self, ctx: core.Context, member: Union[discord.Member, int] = None,
    ):
        _(
            """Shows member rank
        
        If the member is not specified, then shows your rank. You can also find out who \
        is in a particular place by specifying a number."""
        )  # TODO: Переписать
        if ctx.invoked_subcommand is not None:
            return
        if member is None:
            member = ctx.author
        else:
            if member.bot:
                return await ctx.inform(_("This member is a bot."))

        try:
            if isinstance(member, int):
                rank = member
                cursor = (
                    ctx.db.user_stats.find(
                        {"guild_id": ctx.guild.id},
                        {"user_id": True, "exp": True, "lvl": True},
                        sort=[("exp", -1)],
                    )
                    .skip(rank - 1)
                    .limit(1)
                )
                user = cursor.next_object() if await cursor.fetch_next else None
                if user:
                    member = ctx.guild.get_member(
                        user["user_id"]
                    ) or await ctx.guild.fetch_member(user["user_id"])
            else:
                user = await ctx.db.user_stats.find_one(
                    {"guild_id": ctx.guild.id, "user_id": member.id},
                    {"exp": True, "lvl": True},
                )
                rank = await ctx.db.user_stats.count_documents(
                    {"guild_id": ctx.guild.id, "exp": {"$gte": user["exp"]}}
                )
        except (TypeError, KeyError, discord.HTTPException):
            return await ctx.inform(_("Member not found."))

        embed = discord.Embed(colour=self.colour, title=member.display_name)
        embed.add_field(name=_("Level"), value=str(user["lvl"]))
        embed.add_field(
            name=_("Experience"),
            value=f"{user['exp']}/{self.calculate_exp(user['lvl'] + 1)}",
        )
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        rank = medals.get(rank) or f"#{rank}"
        embed.add_field(name=_("Rank"), value=str(rank))
        embed.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=embed)

    @rank.group(name="message", aliases=["msg"], invoke_without_command=True)
    @commands.guild_only()
    async def rank_message(self, ctx: core.Context):
        _("""Disables/Enables auto-message when leveling up""")
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help()

    @rank_message.command(name="enable", aliases=["on"])
    @commands.guild_only()
    async def rank_message_enable(self, ctx: core.Context):
        _("""Enables auto-message when leveling up""")
        result = await ctx.db.user_stats.update_one(
            {"guild_id": ctx.guild.id, "user_id": ctx.author.id},
            {"$set": {"auto_lvl_msg": True}},
        )
        if result.modified_count == 0:
            await ctx.inform(_("Auto-message when leveling up is already enabled."))
        else:
            await ctx.inform(_("Auto-message when leveling up is enabled."))

    @rank_message.command(name="disable", aliases=["off"])
    @commands.guild_only()
    async def rank_message_disable(self, ctx: core.Context):
        _("""Disables auto-message when leveling up""")
        result = await ctx.db.user_stats.update_one(
            {"guild_id": ctx.guild.id, "user_id": ctx.author.id},
            {"$set": {"auto_lvl_msg": False}},
        )
        if result.modified_count == 0:
            await ctx.inform(_("Auto-message when leveling up is already disabled."))
        else:
            await ctx.inform(_("Auto-message when leveling up is disabled."))

    @core.group()
    @commands.guild_only()
    async def top(self, ctx: core.Context):
        _("""Shows guild leaderboard""")
        if ctx.invoked_subcommand is not None:
            return

        cursor = ctx.db.user_stats.find(
            {"guild_id": ctx.guild.id},
            {"user_id": True, "exp": True, "lvl": True},
            sort=[("exp", -1)],
        ).limit(10)
        user_list = dict(enumerate(await cursor.to_list(length=None), start=1))

        if not next(
            (user for user in user_list.values() if user["user_id"] == ctx.author.id),
            False,
        ):
            author = await ctx.db.user_stats.find_one(
                {"guild_id": ctx.guild.id, "user_id": ctx.author.id},
                {"user_id": True, "lvl": True, "exp": True},
            )
            rank = await ctx.db.user_stats.count_documents(
                {"guild_id": ctx.guild.id, "exp": {"$gte": author["exp"]}}
            )
            user_list[rank] = author

        embed = await self.make_leaderboard_embed(user_list)
        embed.title = _("Guild Leaderboard")
        await ctx.send(embed=embed)
