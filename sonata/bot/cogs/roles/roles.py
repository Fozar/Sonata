import asyncio
from typing import Any

import discord
from discord.ext import commands, menus
from pymongo.errors import DuplicateKeyError

from sonata.bot import core
from sonata.bot.core import is_admin
from sonata.db.models.roles import RoleMenu, RoleEmoji


class ManageableRole(commands.Converter):
    async def convert(self, ctx: core.Context, argument):
        role = await commands.RoleConverter().convert(ctx, argument)
        if role.managed:
            raise commands.BadArgument(
                _("I can not manage the following role: {role}").format(role=role)
            )
        me = ctx.guild.me or await ctx.guild.fetch_member(ctx.bot.user.id)
        if me.top_role < role:
            raise commands.BadArgument(
                _("Role `{0}` is above me in the role hierarchy.").format(str(role))
            )

        return role


class RolemenuSource(menus.AsyncIteratorPageSource):
    def __init__(
        self,
        iterator,
        title: str,
        colour: discord.Colour,
        roles,
        get_emoji,
        *,
        per_page,
    ):
        super().__init__(iterator, per_page=per_page)
        self.title = title
        self.colour = colour
        self.roles = roles
        self.get_emoji = get_emoji

    async def format_page(self, menu: menus.MenuPages, entries: Any):
        embed = discord.Embed(title=self.title, colour=self.colour)
        for entry in entries:
            embed.add_field(
                name=entry["name"],
                value="\n".join(
                    f"**{discord.utils.get(self.roles, id=_re['role'])}**: "
                    + str(
                        self.get_emoji(_re["emoji"])
                        if isinstance(_re["emoji"], int)
                        else _re["emoji"]
                    )
                    for _re in entry["roles"]
                ),
            )
        return embed


class Roles(core.Cog, colour=discord.Colour.blurple()):  # TODO: Add description
    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata

    async def search_rolemenu(
        self, guild: discord.Guild, projection: dict = None, limit: int = 10,
    ):
        if projection is None:
            projection = {}
        projection["_id"] = False
        cursor = self.sonata.db.role_menus.find(
            {"guild_id": guild.id}, projection, limit=limit,
        )
        while await cursor.fetch_next:
            yield cursor.next_object()

    async def on_reaction(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        try:
            guild = self.sonata.get_guild(payload.guild_id) or self.sonata.fetch_guild(
                payload.guild_id
            )
            member = (
                payload.member
                or guild.get_member(payload.user_id)
                or await guild.fetch_member(payload.user_id)
            )
            if member.bot:
                return

            message = discord.utils.get(
                self.sonata.cached_messages, id=payload.message_id
            ) or await guild.get_channel(payload.channel_id).fetch_message(
                payload.message_id
            )
            reaction = discord.utils.find(
                lambda r: str(r) == str(payload.emoji), message.reactions
            )
            if not reaction.me:
                return

            me = guild.me or await guild.fetch_member(self.sonata.user.id)
        except discord.HTTPException:
            return

        if not me.guild_permissions.manage_roles:
            return

        emoji = (
            reaction.emoji.id if not isinstance(reaction.emoji, str) else str(reaction)
        )
        cursor = self.sonata.db.role_menus.find(
            {"guild_id": guild.id, "messages": reaction.message.id},
            {"roles": {"$elemMatch": {"emoji": emoji}}},
        )
        while await cursor.fetch_next:
            menu = cursor.next_object()
            role_emoji = menu["roles"][0]
            role = guild.get_role(role_emoji["role"])
            action = (
                member.add_roles
                if payload.event_type == "REACTION_ADD"
                else member.remove_roles
            )
            try:
                await action(role)
            except discord.HTTPException:
                continue

    @core.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.on_reaction(payload)

    @core.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.on_reaction(payload)

    @core.group(aliases=["rm"])
    @commands.check(is_admin)
    async def rolemenu(self, ctx: core.Context):
        _("""Manage role menus""")
        if ctx.invoked_subcommand is not None:
            return

        pages = menus.MenuPages(
            source=RolemenuSource(
                self.search_rolemenu(ctx.guild, {"name": True, "roles": True}),
                _("Rolemenus"),
                self.colour,
                ctx.guild.roles,
                ctx.bot.emoji,
                per_page=10,
            ),
            clear_reactions_after=True,
        )
        try:
            await pages.start(ctx)
        except IndexError:
            await ctx.inform(_("No results were found for your request."))

    @rolemenu.command(
        name="create", aliases=["add"], examples=[_("gender @Male @Female")]
    )
    async def rolemenu_create(
        self,
        ctx: core.Context,
        name: commands.clean_content(),
        *roles: ManageableRole(),
    ):
        _("""Creates a new role menu""")
        if len(roles) < 2:
            return await ctx.inform(_("You must specify at least 2 roles"))

        msg = None
        role_emoji = []

        def format_role_emoji():
            return "\n".join(
                f"**{discord.utils.get(roles, id=_re.role)}**: "
                + str(
                    ctx.bot.emoji(_re.emoji)
                    if isinstance(_re.emoji, int)
                    else _re.emoji
                )
                for _re in role_emoji
            )

        for role in roles:
            content = _(
                "Specify a reaction for the `{role}` role to this message\n\n{role_emoji}"
            ).format(role=role, role_emoji=format_role_emoji(),)
            if msg is None:
                msg = await ctx.send(content)
            else:
                await msg.edit(content=content)
            try:
                reaction, user = await ctx.bot.wait_for(
                    "reaction_add",
                    timeout=60.0,
                    check=lambda r, u: u == ctx.author and r.message.id == msg.id,
                )
            except asyncio.TimeoutError:
                if msg is not None:
                    await msg.delete()
                return await ctx.inform(_("Role menu creation canceled"))
            else:
                emoji = (
                    reaction.emoji.id
                    if not isinstance(reaction.emoji, str)
                    else str(reaction)
                )
                role_emoji.append(RoleEmoji(emoji=emoji, role=role.id))

        await msg.edit(content=format_role_emoji())

        role_menu = RoleMenu(guild_id=ctx.guild.id, name=name, roles=role_emoji)
        try:
            await ctx.db.role_menus.insert_one(role_menu.dict())
        except DuplicateKeyError:
            return await ctx.inform(
                _("A role menu named `{name}` already exists").format(name=name)
            )
        await ctx.inform(_("Role menu named `{name}` saved").format(name=name))

    @rolemenu.command(name="delete", aliases=["remove"], examples=[_("gender")])
    async def rolemenu_delete(self, ctx: core.Context, name: commands.clean_content()):
        _("""Deletes a role menu""")
        result = await ctx.db.role_menus.delete_one(
            {"guild_id": ctx.guild.id, "name": name}
        )
        if result.deleted_count == 0:
            return await ctx.inform(
                _("A role menu named `{name}` was not found").format(name=name)
            )
        await ctx.inform(_("Role menu named `{name}` deleted").format(name=name))

    @rolemenu.command(name="attach")
    @commands.bot_has_guild_permissions(add_reactions=True)
    async def rolemenu_attach(
        self,
        ctx: core.Context,
        name: commands.clean_content(),
        message: discord.Message,
    ):
        _(
            """Starts tracking reactions on the selected message
        
        The member will receive the role if he adds the appropriate reaction to the \
        specified message. The role will be taken away if the member deletes the \
        reaction."""
        )
        role_menu = await ctx.db.role_menus.find_one(
            {"guild_id": ctx.guild.id, "name": name}, {"roles": True}
        )
        if not role_menu:
            return await ctx.inform(
                _("No role menu found named `{name}`").format(name=name)
            )

        cursor = ctx.db.role_menus.find(
            {"guild_id": ctx.guild.id, "messages": message.id}, {"name": True}
        )
        if await cursor.fetch_next:
            rm = cursor.next_object()
            return await ctx.inform(
                _("This message is already in use by role menu `{name}`").format(
                    name=rm["name"]
                )
            )

        for role in role_menu["roles"]:
            emoji = (
                ctx.bot.emoji(role["emoji"])
                if isinstance(role["emoji"], int)
                else role["emoji"]
            )
            await message.add_reaction(emoji)

        await ctx.db.role_menus.update_one(
            {"guild_id": ctx.guild.id, "name": name},
            {"$addToSet": {"messages": message.id}},
        )

        await ctx.inform(_("Role menu `{name}` attached to message").format(name=name))

    @rolemenu.command(name="detach")
    @commands.bot_has_guild_permissions(add_reactions=True)
    async def rolemenu_detach(
        self,
        ctx: core.Context,
        name: commands.clean_content(),
        message: discord.Message,
    ):
        _("""Stops tracking reactions on the selected message""")
        result = await ctx.db.role_menus.update_one(
            {"guild_id": ctx.guild.id, "name": name},
            {"$pull": {"messages": message.id}},
        )
        if result.matched_count == 0:
            return await ctx.inform(
                _("No role menu found named `{name}`").format(name=name)
            )

        if result.modified_count == 0:
            return await ctx.inform(
                _("Role menu named `{name}` not attached to this message.").format(
                    name=name
                )
            )

        await ctx.inform(
            _("Role menu `{name}` detached from message").format(name=name)
        )
