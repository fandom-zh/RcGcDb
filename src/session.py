import aiohttp
from src.config import settings

session = aiohttp.ClientSession(headers=settings["header"])
