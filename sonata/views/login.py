import base64
from urllib.parse import urlencode, quote

from aiohttp import web, FormData
from aiohttp_cors import CorsViewMixin
from aiohttp_session import get_session
from yarl import URL


class Login(web.View, CorsViewMixin):
    async def get(self):
        query = {
            "response_type": "code",
            "client_id": 355591424319946753,
            "scope": "identify guilds",
            "redirect_uri": f"{self.request.url.with_query(None)}/callback",
            "prompt": "none",
        }
        callback_redirect = self.request.query.get("redirect")
        if callback_redirect:
            query["state"] = base64.b64encode(callback_redirect.encode("utf-8")).decode(
                "utf-8"
            )
        location = URL.build(
            path="https://discord.com/api/oauth2/authorize",
            query_string=urlencode(query, quote_via=quote),
            encoded=True,
        )
        raise web.HTTPFound(location)


class LoginCallback(web.View, CorsViewMixin):
    async def get(self):
        code = self.request.query.get("code")
        app = self.request.app
        bot = app.get("bot")
        data = FormData(
            {
                "client_id": "355591424319946753",
                "client_secret": app["config"]["bot"].client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.request.url.with_query(None),
                "scope": "identify guilds",
            }
        )
        async with bot.session.post(
            "https://discord.com/api/oauth2/token", data=data
        ) as r:
            session = await get_session(self.request)
            session['oauth'] = await r.json()
            print(session)

        redirect = self.request.query.get("state")
        redirect = base64.b64decode(redirect).decode("utf-8") if redirect else "/"
        raise web.HTTPFound(redirect)
