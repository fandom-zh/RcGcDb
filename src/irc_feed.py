from __future__ import annotations
import irc.client_aio
import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse, quote

logger = logging.getLogger("rcgcdw.irc_feed")

if TYPE_CHECKING:
	from src.domain import Domain

class AioIRCCat(irc.client_aio.AioSimpleIRCClient):
	def connect(self, *args, **kwargs):
		super().connect(*args, **kwargs)
		self.connection_details = (args, kwargs)

	def __init__(self, targets: dict[str, str], domain_object: Domain):
		irc.client_aio.SimpleIRCClient.__init__(self)
		self.targets = targets
		self.updated = set()  # Storage for edited wikis
		self.updated_discussions = set()
		self.domain = domain_object
		self.connection.buffer_class.errors = "replace"  # Ignore encoding errors
		self.connection_details = None

	def on_welcome(self, connection, event):  # Join IRC channels
		for channel in self.targets.values():
			connection.join(channel)

	def on_pubmsg(self, connection, event):
		if event.target == self.targets["rc"]:
			self.parse_fandom_message(' '.join(event.arguments))
		elif event.target == self.targets["discussion"]:
			self.parse_fandom_discussion(' '.join(event.arguments))

	def on_nicknameinuse(self, c, e):
		c.nick(c.get_nickname() + "_")

	def on_disconnect(self, connection, event):
		self.connect(*self.connection_details[0], **self.connection_details[1])  # attempt to reconnect

	def parse_fandom_message(self, message: str):
		message = message.split("\x035*\x03")
		# print(asyncio.all_tasks())
		half = message[0].find("\x0302http")
		if half == -1:
			return
		message = message[0][half + 3:].strip()
		# print(message)
		url = urlparse(message)
		full_url = "https://"+url.netloc + recognize_langs(url.path)
		try:
			if self.domain[full_url].rc_id != -1:
				self.updated.add(full_url)
				logger.debug("New website appended to the list! {}".format(full_url))
		except KeyError:
			pass


	def parse_fandom_discussion(self, message: str):
		try:
			post = json.loads(message)
		except json.JSONDecodeError:
			logger.warning("Seems like we have invalid JSON in Discussions part, message: {}".format(message))
			return
		if post.get('action', 'unknown') != "deleted":  # ignore deletion events
			url = urlparse(post.get('url'))
			full_url ="https://"+ url.netloc + recognize_langs(url.path)
			if full_url in self.domain:  # POSSIBLE MEMORY LEAK AS WE DON'T HAVE A WAY TO CHECK IF WIKI IS LOOKING FOR DISCUSSIONS OR NOT
				self.updated_discussions.add("https://"+full_url)
				logger.debug("New website appended to the list (discussions)! {}".format(full_url))


def recognize_langs(path):
	lang = ""
	new_path = path.split("/")
	if len(new_path)>2:
		if new_path[1] not in ("wiki", "f"):
			lang = "/"+new_path[1]
	return lang+"/"


