import asyncpg
import logging
from typing import Optional
from src.config import settings

logger = logging.getLogger("rcgcdb.database")
connection: Optional[asyncpg.Connection] = None


async def setup_connection():
    global connection
    # Establish a connection to an existing database named "test"
    # as a "postgres" user.
    logger.debug("Setting up the Database connection...")
    connection = await asyncpg.connect(user=settings["pg_user"], host=settings.get("pg_host", "localhost"),
                                 database=settings.get("pg_db", "rcgcdb"), password=settings.get("pg_pass"))
    logger.debug("Database connection established! Connection: {}".format(connection))


async def shutdown_connection():
    global connection
    await connection.close()
