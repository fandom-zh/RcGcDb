import asyncpg
import logging
from typing import Optional
from src.config import settings

logger = logging.getLogger("rcgcdb.database")
# connection: Optional[asyncpg.Connection] = None


class db_connection:
    connection: Optional[asyncpg.Pool] = None

    async def setup_connection(self):
        # Establish a connection to an existing database named "test"
        # as a "postgres" user.
        logger.debug("Setting up the Database connection...")
        self.connection = await asyncpg.create_pool(user=settings["pg_user"], host=settings.get("pg_host", "localhost"),
                                     database=settings.get("pg_db", "rcgcdb"), password=settings.get("pg_pass"),
                                                    port=settings.get("pg_port", 5432), min_size=10, max_size=40)
        logger.debug("Database connection established! Connection: {}".format(self.connection))

    async def shutdown_connection(self):
        logger.debug("Shutting down database connection...")
        await self.connection.close()

    def pool(self) -> asyncpg.Pool:
        return self.connection

    # Tried to make it a decorator but tbh won't probably work
    # async def in_transaction(self, func):
    #     async def single_transaction():
    #         async with self.connection.acquire() as connection:
    #             async with connection.transaction():
    #                 await func()
    #     return single_transaction

    # async def query(self, string, *arg):
    #     async with self.connection.acquire() as connection:
    #         async with connection.transaction():
    #             return connection.cursor(string, *arg)


db = db_connection()
