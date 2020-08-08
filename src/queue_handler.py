import logging
from src.database import db_cursor, db_connection

logger = logging.getLogger("rcgcdb.queue_handler")


class UpdateDB:
	def __init__(self):
		self.updated = []

	def add(self, wiki, rc_id, feeds=None):
		self.updated.append((wiki, rc_id, feeds))

	def clear_list(self):
		self.updated.clear()

	def update_db(self):
		for update in self.updated:
			if update[2] is None:
				sql = "UPDATE rcgcdw SET rcid = ? WHERE wiki = ? AND rcid != -1"
			else:
				sql = "UPDATE rcgcdw SET postid = ? WHERE wikiid = ?"
			db_cursor.execute(sql, (update[1], update[0]))
		db_connection.commit()
		self.clear_list()


DBHandler = UpdateDB()
