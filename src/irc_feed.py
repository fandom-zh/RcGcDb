from __future__ import annotations

import asyncio
import types

import irc.client_aio
import json
import logging
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import urlparse, quote

logger = logging.getLogger("rcgcdb.irc_feed")

if TYPE_CHECKING:
	from src.domain import Domain


class AioIRCCat(irc.client_aio.AioSimpleIRCClient):
	def connect(self, *args, **kwargs):
		logger.debug("Connecting with {}...".format(args))
		super().connect(*args, **kwargs)
		self.connection_details = (args, kwargs)

	def __init__(self, targets: dict[str, str], domain_object: Domain, rc_callback: Optional[Callable], discussion_callback: Optional[Callable]):
		irc.client_aio.SimpleIRCClient.__init__(self)
		self.targets = targets
		self.updated_wikis: set[str] = set()
		self.updated_discussions: set[str] = set()
		self.rc_callback = rc_callback
		self.discussion_callback = discussion_callback
		self.domain = domain_object
		self.connection.buffer_class.errors = "replace"  # Ignore encoding errors
		self.connection_details = None

	def __str__(self):
		return self.__repr__()

	def __repr__(self):
		return f"<updated_wikis={self.updated_wikis}, updated_discussions={self.updated_discussions}>"

	def on_welcome(self, connection, event):  # Join IRC channels
		logger.debug("Logged into IRC for {domain_name}".format(domain_name=self.domain.name))
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
		# self.connect(*self.connection_details[0], **self.connection_details[1])  # attempt to reconnect
		pass

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
		wiki = self.domain.get_wiki(full_url)  # TODO Perhaps something less performance hurting?
		if wiki and wiki.rc_id != -1:
			self.updated_wikis.add(full_url)
			logger.debug("New website appended to the list! {}".format(full_url))

	def parse_fandom_discussion(self, message: str):
		try:
			post = json.loads(message)
		except json.JSONDecodeError:
			#logger.warning("Seems like we have invalid JSON in Discussions part, message: {}".format(message))
			return
		if post.get('action', 'unknown') != "deleted":  # ignore deletion events
			if isinstance(post.get('url'), bytes) or post.get('url') == "":
				return
			try:
				url = urlparse(post.get('url'))
			except KeyError:
				return
			if isinstance(url.path, bytes):
				return
			lang = recognize_langs(url.path)
			full_url = "https://" + url.netloc + lang
			wiki = self.domain.get_wiki(full_url)
			if wiki and wiki.discussion_id != -1:
				self.updated_discussions.add(full_url)
				logger.debug("New discussion wiki appended to the list! {}".format(full_url))


def recognize_langs(path):
	lang = ""
	new_path = path.split("/")
	if len(new_path)>2:
		if new_path[1] not in ("wiki", "f"):
			lang = "/"+new_path[1]
	return lang+"/"


