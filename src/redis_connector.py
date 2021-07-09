import asyncio
import aioredis
import async_timeout
import logging
from typing import Optional, TYPE_CHECKING
from src.config import settings
from src.wiki import Wiki

logger = logging.getLogger("rcgcdb.redisconnector")

if TYPE_CHECKING:
	from src.domain_manager import DomainManager

class Redis:
    def __init__(self, domain_manager):
        self.pub_connection: Optional[aioredis.connection] = None
        self.stat_connection: Optional[aioredis.connection] = None
        self.domain_manager: DomainManager = domain_manager

    async def reader(self):
        """Based on code from https://aioredis.readthedocs.io/en/latest/getting-started/#pubsub-mode"""
        while True:
            try:
                async with async_timeout.timeout(1):
                    message = await self.pub_connection.get_message(ignore_subscribe_messages=True)
                    if message is not None:
                        print(f"(Reader) Message Received: {message}")
                        logger.debug(f"(Reader) Message Received: {message}")
                        await self.process_changes(message["data"])
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:  # TODO Better handler
                pass
            except aioredis.exceptions.ConnectionError:
                pass
            except asyncio.CancelledError:
                # TODO Send a message about shutdown
                raise NotImplementedError

    async def process_changes(self, data: str):
        data = data.split(" ")
        if data[0] == "REMOVE":
            self.domain_manager.remove_wiki(data[1])  # TODO Add response to source
        elif data[0] == "ADD":  # ADD https://new_wiki.somedamain.com 43 1 where 43 stands for rc_id and 1 for discussion_id
            wiki = Wiki(data[1], int(data[2]), int(data[3]))  # TODO This might raise an issue if non-int value
            await self.domain_manager.new_wiki(wiki)


    async def connect(self):
        self.stat_connection = await aioredis.from_url("redis://" + settings["redis_host"], encoding="UTF-8")

    async def pubsub(self):
        self.pub_connection = self.stat_connection.pubsub()
        await self.pub_connection.subscribe("rcgcdb_updates")
