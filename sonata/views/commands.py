import json

from aiohttp import web

from sonata.views.view import View


class CommandSearch(View):
    async def get(self):
        query = self.request.query.get("query", "")
        try:
            limit = min(int(self.request.query.get("limit")), 20)
        except TypeError:
            raise web.HTTPBadRequest

        self.bot.locale = "ru_RU"
        commands = []
        for cmd in self.bot.walk_commands():
            if len(commands) == limit:
                break
            if cmd.cog.qualified_name == "Owner" or not cmd.enabled or cmd.hidden:
                continue
            if cmd.qualified_name.startswith(query):
                cmd_dict = cmd.to_dict()
                if cmd_dict not in commands:
                    commands.append(cmd.to_dict())
        commands.sort(key=lambda c: c["qualified_name"])

        return web.json_response(
            text=json.dumps(
                commands,
                ensure_ascii=False,
            )
        )