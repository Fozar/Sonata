import aiohttp

from sonata.config import ApiConfig
from sonata.bot.utils import i18n

api_config = ApiConfig()

WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"


async def get_weather(locality: str):
    params = {
        "q": locality,
        "type": "like",
        "units": "metric",
        "lang": i18n.current_locale.get()[:2],
        "APPID": api_config.open_weather,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(WEATHER_URL, params=params) as response:
            data = await response.json()

    if data["cod"] == "404":
        return None
    return data


__all__ = ("get_weather",)
