import asyncio
import collections
import logging
from typing import Union, Optional

import asyncpg

logger = logging.getLogger("rcgcdb.queue_handler")


class UpdateDB:
	def __init__(self):
		self.updated: list[tuple[str, tuple[Union[str, int]]]] = []
		self.db: Optional[] = None

	def add(self, sql_expression):
		self.updated.append(sql_expression)

	def clear_list(self):
		self.updated.clear()

	async def fetch_rows(self, SQLstatement: str, args: Union[str, int]) -> collections.AsyncIterable:
		async with self.db.pool().acquire() as connection:
			async with connection.transaction():
				async for row in connection.cursor(SQLstatement, *args):
					yield row

	async def update_db(self):
		try:
			while True:
				if self.updated:
					async with self.db.pool().acquire() as connection:
						async with connection.transaction():
							for update in self.updated:
								await connection.execute(update[0], *update[1])
							self.clear_list()
				await asyncio.sleep(10.0)
		except asyncio.CancelledError:
			logger.info("Shutting down after updating DB with {} more entries...".format(len(self.updated)))
			async with self.db.pool().acquire() as connection:
				async with connection.transaction():
					for update in self.updated:
						await connection.execute(update[0], *update[1])
					self.clear_list()
			await self.db.shutdown_connection()


dbmanager = UpdateDB()
