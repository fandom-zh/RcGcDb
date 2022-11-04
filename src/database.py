import asyncpg
import logging
from typing import Optional, Callable
from src.config import settings

logger = logging.getLogger("rcgcdb.database")
# connection: Optional[asyncpg.Connection] = None


class db_connection:
    listener_connection: Optional[asyncpg.Connection] = None
    connection_pool: Optional[asyncpg.Pool] = None

    async def create_pubsub_interface(self, callback: Callable):
        await self.listener_connection.add_listener("webhookupdates", callback)

    async def setup_connection(self):
        logger.debug("Setting up the Database connections...")
        # First, setup a separate connection for pub/sub listener
        # It's mainly because I'm afraid that connection pool will be aggressive about inactive connections
        self.listener_connection = await asyncpg.connect(user=settings["pg_user"], host=settings.get("pg_host", "localhost"),
                                                         database=settings.get("pg_db", "rcgcdb"), password=settings.get("pg_pass"),
                                                         port=settings.get("pg_port", 5432))
        self.connection_pool = await asyncpg.create_pool(user=settings["pg_user"], host=settings.get("pg_host", "localhost"),
                                                         database=settings.get("pg_db", "rcgcdb"), password=settings.get("pg_pass"),
                                                         port=settings.get("pg_port", 5432))
        logger.debug("Database connection established! Connection: {}".format(self.connection_pool))

    async def shutdown_connection(self):
        logger.debug("Shutting down database connection...")
        await self.listener_connection.close()
        await self.connection_pool.close()

    def pool(self) -> asyncpg.Pool:
        return self.connection_pool


db = db_connection()
