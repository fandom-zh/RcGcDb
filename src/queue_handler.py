import logging
from src.database import db

logger = logging.getLogger("rcgcdb.queue_handler")


class UpdateDB:
	def __init__(self):
		self.updated = []

	def add(self, wiki, rc_id, feeds=None):
		self.updated.append((wiki, rc_id, feeds))

	def clear_list(self):
		self.updated.clear()

	async def update_db(self):
		async with db.pool().acquire() as connection:
			async with connection.transaction():
				for update in self.updated:
					if update[2] is None:
						sql = "UPDATE rcgcdw SET rcid = $2 WHERE wiki = $1 AND ( rcid != -1 OR rcid IS NULL )"
					else:
						sql = "UPDATE rcgcdw SET postid = $2 WHERE wiki = $1 AND ( postid != '-1' OR postid IS NULL )"
					await connection.execute(sql, update[0], update[1])
				self.clear_list()


DBHandler = UpdateDB()
