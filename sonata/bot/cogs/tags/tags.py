import discord
from discord.ext import commands

from sonata.bot import core
from sonata.bot.utils.converters import TagName
from sonata.db.models import Tag, TagAlias


class Tags(core.Cog):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def is_tag_exists(self, name: str, guild: discord.Guild):
        cursor = self.sonata.db.tags.find(
            {
                "guild_id": guild.id,
                "$or": [{"name": name}, {"aliases": {"$elemMatch": {"alias": name}}}],
            },
            {"name": True},
        )
        return await cursor.fetch_next

    async def get_tag(
        self,
        name: str,
        guild: discord.Guild,
        projection: dict = None,
        inc_uses: bool = False,
    ):
        _filter = {
            "guild_id": guild.id,
            "$or": [{"name": name}, {"aliases": {"$elemMatch": {"alias": name}}}],
        }
        projection["_id"] = False
        if not inc_uses:
            tag = await self.sonata.db.tags.find_one(_filter, projection,)
        else:
            tag = await self.sonata.db.tags.find_one_and_update(
                _filter, {"$inc": {"uses": 1}}, projection
            )
        return tag

    @core.group(invoke_without_command=True)
    @commands.guild_only()
    async def tag(self, ctx: core.Context, *, name: TagName(lower=True)):
        tag = await self.get_tag(name, ctx.guild, {"content": True}, inc_uses=True)
        if not tag:
            return await ctx.inform(_("Tag `{0}` not found.").format(name))
        await ctx.send(tag["content"])

    @tag.command(name="add", aliases=["create"])
    async def tag_add(
        self, ctx: core.Context, name: TagName(), *, content: commands.clean_content()
    ):
        if await self.is_tag_exists(name, ctx.guild):
            return await ctx.inform(_("Tag `{0}` already exists.").format(name))

        tag = Tag(
            created_at=ctx.message.created_at,
            owner_id=ctx.author.id,
            name=name,
            content=content,
            guild_id=ctx.guild.id,
            language=ctx.locale[:2],
        ).dict()
        await ctx.db.tags.insert_one(tag)
        await ctx.inform(_("Tag `{0}` successfully created.").format(name))

    @tag.command(name="alias")
    async def tag_alias(
        self, ctx: core.Context, name: TagName(lower=True), *, alias: TagName()
    ):
        if await self.is_tag_exists(alias, ctx.guild):
            return await ctx.inform(_("Tag `{0}` already exists.").format(alias))

        if not await self.is_tag_exists(name, ctx.guild):
            return await ctx.inform(_("Tag `{0}` not found.").format(name))

        tag = TagAlias(
            created_at=ctx.message.created_at, owner_id=ctx.author.id, alias=alias
        ).dict()
        await ctx.db.tags.update_one(
            {
                "guild_id": ctx.guild.id,
                "$or": [{"name": name}, {"aliases": {"$elemMatch": {"alias": name}}}],
            },
            {"$addToSet": {"aliases": tag}},
        )
        await ctx.inform(
            _(
                "Tag alias `{alias}` that points to `{tag}` successfully created."
            ).format(alias=alias, tag=name)
        )
