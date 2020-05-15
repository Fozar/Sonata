from typing import Union, Any

import discord
from discord.ext import commands, menus

from sonata.bot import core
from sonata.bot.utils.converters import TagName
from sonata.db.models import Tag, TagAlias


class TagSource(menus.AsyncIteratorPageSource):
    def __init__(self, iterator, title: str, colour: discord.Colour, *, per_page):
        super().__init__(iterator, per_page=per_page)
        self.title = title
        self.colour = colour

    async def format_page(self, menu: menus.MenuPages, entries: Any):
        embed = discord.Embed(title=self.title, colour=self.colour)
        offset = menu.current_page * self.per_page
        embed.description = "\n".join(
            f"**{i + 1}**. {v['name']}" for i, v in enumerate(entries, start=offset)
        )
        return embed


class SearchSource(menus.AsyncIteratorPageSource):
    def __init__(
        self, entries, colour: discord.Colour, slice_content: int, *, per_page
    ):
        super().__init__(entries, per_page=per_page)
        self.colour = colour
        self.slice_content = slice_content

    async def format_page(self, menu: menus.MenuPages, entries: Any):
        embed = discord.Embed(title=_("Searching results"), colour=self.colour)
        for entry in entries:
            content = entry["content"]
            value = (
                content
                if len(content) <= self.slice_content
                else content[: self.slice_content] + "..."
            )
            embed.add_field(
                name=entry["name"], value=value,
            )
        return embed


class Tags(core.Cog, colour=discord.Colour.dark_teal()):
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    @staticmethod
    async def _bypass_check(ctx: core.Context):
        return ctx.author.guild_permissions.manage_messages or await ctx.bot.is_owner(
            ctx.author
        )

    async def is_tag_exists(self, name: str, guild: discord.Guild):
        cursor = self.sonata.db.tags.find(
            {
                "guild_id": guild.id,
                "$or": [{"name": name}, {"aliases": {"$elemMatch": {"alias": name}}}],
            },
            {"_id": False, "name": True},
        )
        return await cursor.fetch_next

    async def is_alias_exists(self, name: str, guild: discord.Guild):
        cursor = self.sonata.db.tags.find(
            {"guild_id": guild.id, "aliases": {"$elemMatch": {"alias": name}}},
            {"_id": False, "name": True},
        )
        return await cursor.fetch_next

    async def is_tag_owner(
        self, name: str, guild: discord.Guild, user: Union[discord.User, discord.Member]
    ):
        cursor = self.sonata.db.tags.find(
            {"guild_id": guild.id, "name": name, "owner_id": user.id},
            {"_id": False, "name": True},
        )
        return await cursor.fetch_next

    async def is_alias_owner(
        self, name: str, guild: discord.Guild, user: Union[discord.User, discord.Member]
    ):
        cursor = self.sonata.db.tags.find(
            {
                "guild_id": guild.id,
                "aliases": {"$elemMatch": {"alias": name, "owner_id": user.id}},
            },
            {"_id": False, "name": True},
        )
        return await cursor.fetch_next

    async def get_tag(
        self,
        name: str,
        guild: discord.Guild,
        projection: dict = None,
        inc_uses: bool = False,
    ):
        if projection is None:
            projection = {}
        projection["_id"] = False
        _filter = {
            "guild_id": guild.id,
            "$or": [{"name": name}, {"aliases": {"$elemMatch": {"alias": name}}}],
        }
        if not inc_uses:
            tag = await self.sonata.db.tags.find_one(_filter, projection,)
        else:
            tag = await self.sonata.db.tags.find_one_and_update(
                _filter, {"$inc": {"uses": 1}}, projection
            )
        return tag

    async def get_alias(self, name: str, guild: discord.Guild, projection: dict = None):
        if projection is None:
            projection = {}
        projection["_id"] = False
        return await self.sonata.db.tags.find_one(
            {"guild_id": guild.id, "aliases": {"$elemMatch": {"alias": name}}},
            projection,
        )

    async def get_all_tags(
        self,
        guild: discord.Guild,
        query: dict = None,
        projection: dict = None,
        limit: int = 20,
    ):
        if projection is None:
            projection = {}
        if query is None:
            query = {}
        projection["_id"] = False
        query["guild_id"] = guild.id
        cursor = self.sonata.db.tags.find(
            query, projection, limit=limit, sort=[("name", 1)]
        )
        while await cursor.fetch_next:
            yield cursor.next_object()

    async def search_tags(
        self,
        query: str,
        guild: discord.Guild,
        locale: str = "en_US",
        projection: dict = None,
        limit: int = 20,
    ):
        if projection is None:
            projection = {}
        projection["_id"] = False
        cursor = self.sonata.db.tags.find(
            {
                "guild_id": guild.id,
                "$text": {"$search": query, "$language": locale[:2]},
            },
            projection,
            limit=limit,
        )
        while await cursor.fetch_next:
            yield cursor.next_object()

    @core.group(invoke_without_command=True)
    @commands.guild_only()
    async def tag(self, ctx: core.Context, *, name: TagName() = None):
        _("""Returns the text with the specified tag""")
        name = name.strip('" ')
        if not name:
            return await ctx.send_help()
        tag = await self.get_tag(name, ctx.guild, {"content": True}, inc_uses=True)
        if tag:
            return await ctx.send(tag["content"])

        results = []
        async for result in self.search_tags(
            name, ctx.guild, ctx.locale, {"name": True}
        ):
            results.append(result)
        if not results:
            return await ctx.inform(_("Tag `{0}` not found.").format(name))

        await ctx.inform(
            _("**Did you mean**:\n")
            + "\n".join(
                [
                    f"**{number}.** " + res["name"]
                    for number, res in zip(range(1, len(results) + 1), results)
                ]
            )
        )

    @tag.command(name="add", aliases=["create"])
    async def tag_add(
        self, ctx: core.Context, name: TagName(), *, content: commands.clean_content()
    ):
        _(
            """Creates new tag

        This tag will belong to you and will be available only in this guild.
        You must enclose the name in double quotation marks if it consists of more than \
        one word."""
        )
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
    async def tag_alias(self, ctx: core.Context, name: TagName(), *, alias: TagName()):
        _(
            """Creates new tag alias
        
        This alias will belong to you and will be available only in this guild.
        Removing the original tag will also remove the alias.
        You must enclose the name in double quotation marks if it consists of more than \
        one word."""
        )
        alias = alias.strip('" ')
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

    @tag.command(name="all", ignore_extra=False)
    async def tag_all(self, ctx: core.Context):
        _("""Lists all tags""")
        pages = menus.MenuPages(
            source=TagSource(
                self.get_all_tags(ctx.guild, projection={"name": True}, limit=0),
                _("Tag list"),
                ctx.colour,
                per_page=20,
            ),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    @tag.command(name="delete", aliases=["remove"])
    async def tag_delete(self, ctx: core.Context, *, name: TagName()):
        _("""Deletes your tag or alias""")
        is_alias = await self.is_alias_exists(name, ctx.guild)
        if not await self.is_tag_exists(name, ctx.guild) and not is_alias:
            return await ctx.inform(_("Tag `{0}` not found.").format(name))

        bypass_check = await self._bypass_check(ctx)
        if is_alias:
            if bypass_check or await self.is_alias_owner(name, ctx.guild, ctx.author):
                await ctx.db.tags.update_one(
                    {
                        "guild_id": ctx.guild.id,
                        "aliases": {"$elemMatch": {"alias": name}},
                    },
                    {"$pull": {"aliases": {"alias": name}}},
                )
                await ctx.inform(
                    _("Tag alias `{0}` successfully deleted.").format(name)
                )
            else:
                await ctx.inform(_("You are not the owner of this tag alias."))
        else:
            if bypass_check or await self.is_tag_owner(name, ctx.guild, ctx.author):
                await ctx.db.tags.delete_one({"guild_id": ctx.guild.id, "name": name})
                await ctx.inform(_("Tag `{0}` successfully deleted.").format(name))
            else:
                await ctx.inform(_("You are not the owner of this tag."))

    @tag.command(name="edit")
    async def tag_edit(
        self,
        ctx: core.Context,
        name: TagName(),
        *,
        new_content: commands.clean_content(),
    ):
        _(
            """Edits content of your tag
        
        Be careful, the command completely replaces the content of the tag.
        You must enclose the name in double quotation marks if it consists of more than \
        one word."""
        )
        tag = await self.get_tag(name, ctx.guild, {"name": True})
        if not tag:
            return await ctx.inform(_("Tag `{0}` not found.").format(name))

        if not await self._bypass_check(ctx) and not await self.is_tag_owner(
            tag["name"], ctx.guild, ctx.author
        ):
            return await ctx.inform(_("You are not the owner of this tag."))

        await ctx.db.tags.update_one(
            {"name": tag["name"]}, {"$set": {"content": new_content}}
        )
        await ctx.inform(_("Tag content changed."))

    @tag.command(name="list")
    async def tag_list(self, ctx: core.Context, member: discord.Member = None):
        _(
            """Lists the tags of the specified member
        
        If the member is not specified, lists author tags."""
        )
        if member is None:
            member = ctx.author
        pages = menus.MenuPages(
            source=TagSource(
                self.get_all_tags(
                    ctx.guild, {"owner_id": member.id}, {"name": True}, limit=0
                ),
                _("Tag list"),
                ctx.colour,
                per_page=20,
            ),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    @tag.command(name="raw")
    async def tag_raw(self, ctx: core.Context, *, name: TagName()):
        _("""Returns the raw content with the specified tag""")
        tag = await self.get_tag(name, ctx.guild, {"content": True})
        if not tag:
            return await ctx.inform(_("Tag `{0}` not found.").format(name))

        return await ctx.send(discord.utils.escape_markdown(tag["content"]))

    @tag.command(name="search")
    async def tag_search(self, ctx: core.Context, *, query: str):
        _("""Searches for tags""")
        pages = menus.MenuPages(
            source=SearchSource(
                self.search_tags(
                    query,
                    ctx.guild,
                    ctx.locale,
                    {"name": True, "content": True},
                    limit=0,
                ),
                ctx.colour,
                100,
                per_page=24,
            ),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    @core.command()
    @commands.guild_only()
    async def tags(self, ctx: core.Context):
        _("""An alias for tag all command""")
        await ctx.invoke(self.tag_all)
