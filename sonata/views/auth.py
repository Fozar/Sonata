import base64
from urllib.parse import urlencode, quote

from aiohttp import web, FormData
from aiohttp_cors import CorsViewMixin
from aiohttp_security import remember, is_anonymous
from aiohttp_session import get_session
from yarl import URL


class Auth(web.View, CorsViewMixin):
    async def get(self):
        uri = self.request.url.with_query(None)
        if not await is_anonymous(self.request):
            raise web.HTTPFound(
                uri.origin().with_path(self.request.query.get("redirect") or "/")
            )

        if not self.request.app["debug"]:
            uri = uri.with_scheme("https")
        query = {
            "response_type": "code",
            "client_id": 355591424319946753,
            "scope": "identify guilds",
            "redirect_uri": f"{uri}/callback",
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


class AuthCallback(web.View, CorsViewMixin):
    async def get(self):
        code = self.request.query.get("code")
        if not code:
            raise web.HTTPBadRequest

        app = self.request.app
        bot = app.get("bot")
        uri = self.request.url.with_query(None)
        if not self.request.app["debug"]:
            uri = uri.with_scheme("https")
        user = FormData(
            {
                "client_id": "355591424319946753",
                "client_secret": app["config"]["bot"].client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": uri,
                "scope": "identify guilds",
            }
        )
        async with bot.session.post(
            "https://discord.com/api/oauth2/token", data=user
        ) as r:
            if r.status != 200:
                raise web.HTTPBadRequest
            oauth = await r.json()
        if "error" in oauth:
            raise web.HTTPBadRequest(reason=oauth["error"])
        async with bot.session.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {oauth['access_token']}"},
        ) as r:
            if r.status != 200:
                raise web.HTTPBadGateway
            user = await r.json()
        session = await get_session(self.request)
        session["oauth"] = oauth
        redirect = self.request.query.get("state")
        redirect = (
            base64.urlsafe_b64decode(redirect).decode("utf-8") if redirect else "/"
        )
        response = web.Response(
            text=(
                "<html><script type=\"text/javascript\">"
                "window.localStorage.setItem('LoggedIn', true);\n"
                f"window.location.href = '{redirect}';\n"
                "</script></html>"
            ),
            content_type="text/html",
        )
        await remember(self.request, response, user["id"])
        return response
