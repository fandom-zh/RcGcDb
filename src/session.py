import aiohttp
from src.config import settings
session = None


async def start_session():
	global session
	session = aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(5.0))
