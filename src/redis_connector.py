import asyncio
import aioredis
from src.config import settings


class Redis:
    def __init__(self):
        self.connection = None

    async def connect(self):
        self.connection = await aioredis.create_pool("redis://" + settings["redis_host"], encoding="UTF-8")


redis = Redis()
