import math
import random

import discord
from discord import abc
from typing import Dict, Union

from discord.ext import commands

from sonata.bot import core
from sonata.db.models import Guild, User, Command


class Stats(
    core.Cog, description=_("""Sonata statistics"""), colour=discord.Colour(0xF5A623)
):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @staticmethod
    def calculate_exp(lvl: int):
        return math.ceil(100 * lvl ** 2 - 100 * lvl) + 100

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

    @core.Cog.listener()
    async def on_ready(self):
        for guild in self.sonata.guilds:
            await self.on_guild_join(guild)
        for command in self.sonata.walk_commands():
            guild_conf = self.sonata.db.commands.find(
                {"name": command.qualified_name}, {"name": True}
            ).limit(1)
            if not await guild_conf.fetch_next:
                command_conf = Command(
                    name=command.qualified_name,
                    cog=command.cog.qualified_name if command.cog else None,
                    enabled=command.enabled,
                ).dict()
                await self.sonata.db.commands.insert_one(command_conf)

    @core.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.sonata.should_reply(message):
            return

        if message.guild:
            guild = await self.sonata.db.guilds.find_one_and_update(
                {"id": message.guild.id},
                {
                    "$currentDate": {"last_message_at": True},
                    "$inc": {"total_messages": 1},
                },
                {"_id": False, "leveling": True},
            )
            leveling = guild["leveling"]
        else:
            leveling = False

        if leveling:
            user = await self.sonata.db.users.find_one_and_update(
                {"id": message.author.id},
                {"$inc": {"total_messages": 1}},
                {"_id": False, "last_exp_at": True, "exp": True, "lvl": True},
            )
            if (
                user["last_exp_at"] is None
                or (message.created_at - user["last_exp_at"]).total_seconds() >= 60
            ):
                exp = random.randint(5, 15) * int(1 + user["lvl"] / 100)
                user["exp"] += exp
                next_lvl = user["lvl"] + 1
                update = {
                    "$inc": {"exp": exp},
                    "$set": {"last_exp_at": message.created_at},
                }
                if user["exp"] >= self.calculate_exp(next_lvl):
                    user["lvl"] = next_lvl
                    update["$inc"]["lvl"] = 1
                await self.sonata.db.users.update_one({"id": message.author.id}, update)
                if user["lvl"] == next_lvl:
                    await self.sonata.set_locale(message)
                    rank = await self.sonata.db.users.count_documents(
                        {"guilds": message.guild.id, "exp": {"$gte": user["exp"]}}
                    )
                    embed = self.make_lvlup_embed(
                        message.author, user["lvl"], user["exp"], rank
                    )
                    await message.channel.send(embed=embed)
        else:
            await self.sonata.db.users.update_one(
                {"id": message.author.id}, {"$inc": {"total_messages": 1}}
            )

    @core.Cog.listener()
    async def on_command(self, ctx: core.Context):
        await ctx.db.commands.update_one(
            {"name": ctx.command.qualified_name}, {"$inc": {"invocation_counter": 1}}
        )
        await ctx.db.users.update_one(
            {"id": ctx.author.id}, {"$inc": {"commands_invoked": 1}}
        )
        if ctx.guild:
            await ctx.db.guilds.update_one(
                {"id": ctx.guild.id}, {"$inc": {"commands_invoked": 1}}
            )

    # noinspection PyUnusedLocal
    @core.Cog.listener()
    async def on_command_error(self, ctx: core.Context, exception: Exception):
        if ctx.command:
            await ctx.db.commands.update_one(
                {"name": ctx.command.qualified_name}, {"$inc": {"error_count": 1}}
            )

    @core.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_conf = await self.sonata.db.guilds.find_one_and_update(
            {"id": guild.id}, {"$set": {"name": guild.name, "left": None}}
        )
        if not guild_conf:
            guild_conf = Guild(id=guild.id, name=guild.name).dict()
            await self.sonata.db.guilds.insert_one(guild_conf)
        for member in guild.members:
            await self.on_member_join(member)

    @core.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self.sonata.db.guilds.update_one(
            {"id": guild.id}, {"$currentDate": {"left": True}}
        )

    @core.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            await self.sonata.db.guilds.update_one(
                {"id": before.id}, {"$set": {"name": after.name}}
            )

    @core.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        result = await self.sonata.db.users.update_one(
            {"id": member.id},
            {"$set": {"name": str(member)}, "$addToSet": {"guilds": member.guild.id}},
        )
        if result.matched_count == 0:
            member_conf = User(id=member.id, name=str(member)).dict()
            await self.sonata.db.users.insert_one(member_conf)

    @core.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await self.sonata.db.users.update_one(
            {"id": member.id}, {"$pull": {"guilds": member.guild.id}}
        )

    @core.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if str(before) != str(after):
            await self.sonata.db.users.update_one(
                {"id": before.id}, {"$set": {"name": str(after)}}
            )

    @core.Cog.listener()
    async def on_private_channel_create(self, channel: abc.PrivateChannel):
        if isinstance(channel, discord.DMChannel):
            user = channel.recipient
            user_conf = self.sonata.db.users.find({"id": user.id}, {"id": True}).limit(
                1
            )
            if not await user_conf.fetch_next:
                user_conf = User(id=user.id, name=str(user)).dict()
                await self.sonata.db.users.insert_one(user_conf)

    @core.command()
    @commands.guild_only()
    async def rank(
        self,
        ctx: core.Context,
        member: Union[discord.Member, int] = None,
    ):
        _("""Shows your guild rank""")
        if member is None:
            member = ctx.author
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"leveling": True})
        if not guild["leveling"]:
            return await ctx.inform(_("This guild has a level system disabled."))
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

        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"leveling": True})
        if not guild["leveling"]:
            return await ctx.inform(_("This guild has a level system disabled."))

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
        guild = await ctx.db.guilds.find_one({"id": ctx.guild.id}, {"leveling": True})
        if (
            not next(
                (user for user in user_list.values() if user["id"] == ctx.author.id),
                False,
            )
            and guild["leveling"]
        ):
            author = await ctx.db.users.find_one(
                {"id": ctx.author.id}, {"id": True, "lvl": True, "exp": True}
            )
            rank = await ctx.db.users.count_documents({"exp": {"$gte": author["exp"]}})
            user_list[rank] = author
        embed = self.make_leaderboard_embed(user_list)
        embed.title = _("Global Leaderboard")
        await ctx.send(embed=embed)
