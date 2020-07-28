import logging
from src.database import db_cursor, db_connection

logger = logging.getLogger("rcgcdb.queue_handler")


class UpdateDB:
	def __init__(self):
		self.updated = []

	def add(self, wiki, rc_id):
		self.updated.append((wiki, rc_id))

	def clear_list(self):
		self.updated.clear()

	def update_db(self):
		for update in self.updated:
			db_cursor.execute("UPDATE rcgcdw SET rcid = ? WHERE wiki = ?", (update[1], update[0],))
		db_connection.commit()
		self.clear_list()


DBHandler = UpdateDB()
