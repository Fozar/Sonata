import aiohttp


class DogAPI:
    base_url = "https://dog.ceo/api"
    breeds_list_endpoint = "/breeds/list"
    random_all_breeds_endpoint = "/breeds/image/random"
    random_breed_endpoint = "/breed/{0}/images/random"

    async def _api_request(self, endpoint):
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url + endpoint) as response:
                return await response.json()

    async def list(self):
        return await self._api_request(self.breeds_list_endpoint)

    async def random(self, breed=None):
        if breed is None:
            return await self._api_request(self.random_all_breeds_endpoint)

        return await self._api_request(self.random_breed_endpoint.format(breed))
