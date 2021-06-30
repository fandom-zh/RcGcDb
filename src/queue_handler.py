import asyncio
import logging
from src.database import db

logger = logging.getLogger("rcgcdb.queue_handler")


class UpdateDB:
	def __init__(self):
		self.updated = []

	def add(self, sql_expression):
		self.updated.append(sql_expression)

	def clear_list(self):
		self.updated.clear()

	async def update_db(self):
		try:
			while True:
				if self.updated:
					async with db.pool().acquire() as connection:
						async with connection.transaction():
							for update in self.updated:
								await connection.execute(update)
							self.clear_list()
				await asyncio.sleep(10.0)
		except asyncio.CancelledError:
			logger.info("Shutting down after updating DB with {} more entries...".format(len(self.updated)))
			async with db.pool().acquire() as connection:
				async with connection.transaction():
					for update in self.updated:
						await connection.execute(update)
					self.clear_list()
			await db.shutdown_connection()


DBHandler = UpdateDB()
