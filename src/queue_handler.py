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
			update_type = "postid" if update[2] is not None else "rcid"
			db_cursor.execute("UPDATE rcgcdw SET {} = ? WHERE wiki = ? AND NOT ? = -1".format(update_type), (update[1], update[0], update_type))
		db_connection.commit()
		self.clear_list()


DBHandler = UpdateDB()
