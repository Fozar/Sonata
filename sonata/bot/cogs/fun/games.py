from sonata.bot import core


class Games(core.Cog):
    @core.group(enabled=False)
    async def game(self, ctx: core.Context):
        _("""Starts a game session""")
        if ctx.invoked_subcommand is not None:
            return
        await ctx.send_help()
