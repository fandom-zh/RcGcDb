import asyncio
import re
import irc.client_aio
import json
import logging
from urllib.parse import urlparse, quote

logger = logging.getLogger("rcgcdw.irc_feed")


class AioIRCCat(irc.client_aio.AioSimpleIRCClient):
	def connect(self, *args, **kwargs):
		super().connect(*args, **kwargs)
		self.connection_details = (args, kwargs)

	def __init__(self, targets, all_wikis):
		irc.client_aio.SimpleIRCClient.__init__(self)
		self.targets = targets
		self.updated = set()  # Storage for edited wikis
		self.updated_discussions = set()
		self.wikis = all_wikis
		self.connection.buffer_class.errors = "replace"  # Ignore encoding errors
		self.connection_details = None
		self.active = True
		self.activity_tester = asyncio.get_event_loop().create_task(self.testactivity())

	def on_welcome(self, connection, event):  # Join IRC channels
		for channel in self.targets.values():
			if channel is not None:
				connection.join(channel)

	def on_pubmsg(self, connection, event):
		self.active = True
		if event.target == self.targets["rc"]:
			self.parse_rc_message(' '.join(event.arguments))
		elif event.target == self.targets["discussion"]:
			self.parse_discussion_message(' '.join(event.arguments))

	def on_nicknameinuse(self, c, e):
		c.nick(c.get_nickname() + "_")

	def on_disconnect(self, connection, event):
		self.connect(*self.connection_details[0], **self.connection_details[1])  # attempt to reconnect

	def parse_rc_message(self, message: str):
		message = message.split("\x035*\x03")
		# print(asyncio.all_tasks())
		message[0] = re.sub(r"^(\w+)wiki $", "\x0302https://\\1.miraheze.org/w/", message[0]) # Convert miraheze database name to wiki script path
		half = message[0].find("\x0302http")
		if half == -1:
			return
		message = message[0][half + 3:].strip()
		# print(message)
		url = urlparse(message)
		full_url = "https://"+url.netloc + recognize_langs(url.path)
		if full_url in self.wikis and self.wikis[full_url].rc_active != -1:
			self.updated.add(full_url)
			logger.debug("New website appended to the list! {}".format(full_url))

	def parse_discussion_message(self, message: str):
		try:
			post = json.loads(message)
		except json.JSONDecodeError:
			logger.warning("Seems like we have invalid JSON in Discussions part, message: {}".format(message))
			return
		if post.get('action', 'unknown') != "deleted":  # ignore deletion events
			url = urlparse(post.get('url'))
			full_url ="https://"+ url.netloc + recognize_langs(url.path)
			if full_url in self.wikis:  # POSSIBLE MEMORY LEAK AS WE DON'T HAVE A WAY TO CHECK IF WIKI IS LOOKING FOR DISCUSSIONS OR NOT
				self.updated_discussions.add("https://"+full_url)
				logger.debug("New website appended to the list (discussions)! {}".format(full_url))

	async def testactivity(self):
		while True:
			await asyncio.sleep(100.0)
			if not self.active:
				logger.error("There were no new messages in the feed!")
				self.on_disconnect(None, None)
			self.active = False

def recognize_langs(path):
	lang = ""
	new_path = path.split("/")
	if len(new_path)>2:
		if new_path[1] not in ("wiki", "f"):
			lang = "/"+new_path[1]
	return lang+"/"


