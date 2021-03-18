import asyncpg
from typing import Any, Union, Optional
from src.config import settings

connection: Optional[asyncpg.Connection] = None


async def setup_connection():
    global connection
    # Establish a connection to an existing database named "test"
    # as a "postgres" user.
    connection: asyncpg.connection = await asyncpg.connect(user=settings["pg_user"], host=settings.get("pg_host", "localhost"),
                                 database=settings.get("pg_db", "RcGcDb"), password=settings.get("pg_pass"))


async def shutdown_connection():
    global connection
    await connection.close()
