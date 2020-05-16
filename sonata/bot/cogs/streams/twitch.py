import json
from datetime import timedelta

from aiohttp import web
from aiohttp.web_request import Request
from discord.ext import commands

from sonata.bot import core
from sonata.db.models import TwitchSubscription

HELIX_API = "https://api.twitch.tv/helix"
STREAMS_URL = HELIX_API + "/streams"
USERS_URL = HELIX_API + "/users"
WEBHOOKS_HUB_URL = HELIX_API + "/webhooks/hub"


CALLBACK_URL = "https://www.sonata.fun/api/wh/twitch"


class TwitchUser(commands.Converter):
    async def convert(self, ctx: core.Context, argument):
        try:
            params = {"id": int(argument)}
        except ValueError:
            params = {"login": argument}

        async with ctx.session.get(
            USERS_URL,
            headers={
                "Client-ID": ctx.bot.config["twitch"].client_id,
                "Authorization": "Bearer " + ctx.bot.config["twitch"].bearer_token,
            },
            params=params,
        ) as resp:
            j = await resp.json()
            try:
                data = j["data"]
            except KeyError:
                raise commands.BadArgument(_("Twitch user is not found"))
        return data[0]


class TwitchMixin(core.Cog):
    events = {"streams": "stream_changed"}

    def __init__(self, sonata: core.Sonata):
        self.sonata = sonata
        app = sonata.app
        cors = app["cors"]
        resource = cors.add(app.router.add_resource(r"/wh/twitch/{topic}/{id}"))
        cors.add(resource.add_route("GET", self.handler_get))
        cors.add(resource.add_route("POST", self.handler_post))

    async def handler_get(self, request: Request):
        query = request.query
        try:
            if query["hub.mode"] == "denied":
                return web.Response(text="OK", status=200)

            if query["hub.challenge"]:
                return web.Response(
                    body=query["hub.challenge"], content_type="text/plain"
                )
        except KeyError:
            return web.Response(text="Bad Request", status=400)

        return web.Response(text="OK", status=200)

    async def handler_post(self, request: Request):
        try:
            j = await request.json()
            data = j["data"]
        except json.JSONDecodeError:
            return web.Response(text="Bad Request", status=400)

        self.sonata.dispatch(
            self.events[request.match_info["topic"]], data, request.match_info["id"]
        )

        return web.Response(text="OK", status=200)

    async def on_stream_changed(self, data: dict, user_id: str):
        pass

    @core.group(invoke_without_command=True)
    async def twitch(self, ctx: core.Context):
        await ctx.send_help()

    @twitch.command(name="add")
    async def twitch_add(self, ctx: core.Context, user: TwitchUser()):
        now = ctx.message.created_at
        topic = STREAMS_URL + f"?user_id={user['id']}"
        callback = CALLBACK_URL + f"/{topic}/{user['id']}"
        sub = TwitchSubscription(
            created_at=now,
            guild_id=ctx.guild.id,
            id=user["id"],
            login=user["login"],
            topic=topic,
            callback=callback,
            expires_at=now + timedelta(seconds=864000),
        ).dict()
        print(sub)
        params = {
            "hub.callback": sub["callback"],
            "hub.mode": "subscribe",
            "hub.topic": sub["topic"],
            "hub.lease_seconds": 864000,
        }
        async with ctx.typing():
            async with ctx.session.post(
                WEBHOOKS_HUB_URL,
                headers={
                    "Client-ID": ctx.bot.config["twitch"].client_id,
                    "Authorization": "Bearer " + ctx.bot.config["twitch"].bearer_token,
                },
                params=params,
            ) as resp:
                if resp.status != 202:
                    return await ctx.inform(_("An error occurred while subscribing."))
                print("success")
        await ctx.db.twitch_subs.update_one(
            {"guild_id": sub.pop("guild_id"), "id": sub.pop("id")},
            {"$setOnInsert": sub},
            upsert=True,
        )
        await ctx.inform(
            _("User {0} is now tracked in this guild.").format(sub["login"])
        )
