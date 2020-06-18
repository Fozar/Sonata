from aiohttp import web
from aiohttp.web_request import Request
from aiohttp_cors import CorsViewMixin


class View(web.View, CorsViewMixin):
    def __init__(self, request: Request):
        super().__init__(request)
        self.bot = self.request.app["bot"]
