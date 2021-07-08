import asyncio
import aioredis
import async_timeout
import logging
from typing import Optional
from src.config import settings

logger = logging.getLogger("rcgcdb.redisconnector")

class Redis:
    def __init__(self):
        self.pub_connection: Optional[aioredis.connection] = None
        self.stat_connection: Optional[aioredis.connection] = None

    async def reader(self):
        """Based on code from https://aioredis.readthedocs.io/en/latest/getting-started/#pubsub-mode"""
        while True:
            try:
                async with async_timeout.timeout(1):
                    message = await self.pub_connection.get_message(ignore_subscribe_messages=True)
                    if message is not None:
                        print(f"(Reader) Message Received: {message}")
                        logger.debug(f"(Reader) Message Received: {message}")
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:  # TODO Better handler
                pass
            except aioredis.exceptions.ConnectionError:
                pass

    async def connect(self):
        self.stat_connection = await aioredis.from_url("redis://" + settings["redis_host"], encoding="UTF-8")

    async def pubsub(self):
        self.pub_connection = self.stat_connection.pubsub()
        await self.pub_connection.subscribe("rcgcdb_updates")
        asyncio.create_task(self.reader())


redis = Redis()
