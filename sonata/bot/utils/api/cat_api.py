import aiohttp

from sonata.config import ApiConfig

api_config = ApiConfig()


class CatAPI:
    base_url = "https://api.thecatapi.com/v1"
    images_search_endpoint = "/images/search"

    async def _api_request(self, endpoint):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.base_url + endpoint, headers={"x-api-key": api_config.cat_api}
            ) as response:
                data = await response.json()
        return data[0]

    async def random(self):
        return await self._api_request(self.images_search_endpoint)
