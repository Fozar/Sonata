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

    def make_leaderboard_embed(self, user_list: Dict[int, Dict[str, int]]):
        embed = discord.Embed(colour=self.colour)
        for rank, user_conf in user_list.items():
            user = self.sonata.get_user(user_conf["id"])
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
        await self.sonata.set_locale(message)
        rank = await self.sonata.db.users.count_documents(
            {"guilds": message.guild.id, "exp": {"$gte": exp}}
        )
        embed = self.make_lvlup_embed(message.author, lvl, exp, rank)
        await message.channel.send(embed=embed)

    async def update_user_exp(self, message, exp, lvl):
        exp = random.randint(5, 15) * int(1 + lvl / 100) + exp
        update = {
            "$set": {"last_exp_at": message.created_at, "exp": exp},
        }
        next_lvl = lvl + 1
        if exp >= self.calculate_exp(next_lvl):
            lvl = next_lvl
            update["$set"]["lvl"] = lvl
        await self.sonata.db.users.update_one({"id": message.author.id}, update)
        if lvl == next_lvl:
            await self.lvl_up(message, exp, lvl)

    @core.command()
    @commands.guild_only()
    async def rank(
        self, ctx: core.Context, member: Union[discord.Member, int] = None,
    ):
        _("""Shows your guild rank""")
        if member is None:
            member = ctx.author
        if isinstance(member, int):
            rank = member
            cursor = (
                ctx.db.users.find(
                    {"guilds": ctx.guild.id},
                    {"id": True, "exp": True, "lvl": True},
                    sort=[("exp", -1)],
                )
                .skip(rank - 1)
                .limit(1)
            )
            user = cursor.next_object() if await cursor.fetch_next else None
            if user:
                member = ctx.guild.get_member(user["id"])
        else:
            user = await ctx.db.users.find_one(
                {"id": member.id}, {"exp": True, "lvl": True}
            )
            rank = await ctx.db.users.count_documents(
                {"guilds": ctx.guild.id, "exp": {"$gte": user["exp"]}}
            )
        if not user:
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

    @core.group()
    async def top(self, ctx: core.Context):
        _("""Shows guild leaderboard""")
        if ctx.invoked_subcommand is not None:
            return

        cursor = ctx.db.users.find(
            {"guilds": ctx.guild.id},
            {"id": True, "exp": True, "lvl": True},
            sort=[("exp", -1)],
        ).limit(10)
        user_list = dict(enumerate(await cursor.to_list(length=None), start=1))

        if not next(
            (user for user in user_list.values() if user["id"] == ctx.author.id), False
        ):
            author = await ctx.db.users.find_one(
                {"id": ctx.author.id}, {"id": True, "lvl": True, "exp": True}
            )
            rank = await ctx.db.users.count_documents(
                {"guilds": ctx.guild.id, "exp": {"$gte": author["exp"]}}
            )
            user_list[rank] = author

        embed = self.make_leaderboard_embed(user_list)
        embed.title = _("Guild Leaderboard")
        await ctx.send(embed=embed)

    @top.command(name="global")
    async def top_global(self, ctx: core.Context):
        _("""Shows global leaderboard""")
        cursor = ctx.db.users.find(
            {}, {"id": True, "exp": True, "lvl": True}, sort=[("exp", -1)],
        ).limit(10)
        user_list = dict(enumerate(await cursor.to_list(length=None), start=1))
        if not next(
            (user for user in user_list.values() if user["id"] == ctx.author.id), False,
        ):
            author = await ctx.db.users.find_one(
                {"id": ctx.author.id}, {"id": True, "lvl": True, "exp": True}
            )
            rank = await ctx.db.users.count_documents({"exp": {"$gte": author["exp"]}})
            user_list[rank] = author
        embed = self.make_leaderboard_embed(user_list)
        embed.title = _("Global Leaderboard")
        await ctx.send(embed=embed)
