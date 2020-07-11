import logging

logger = logging.getLogger("rcgcdb.queue_handler")

class UpdateDB():
	def __init__(self):
		self.updated = []

	def add(self, wiki, rc_id):
		self.updated.append((wiki, rc_id))

	def clear_list(self):
		self.updated.clear()

	def update_db(self):
		for update in self.updated:
