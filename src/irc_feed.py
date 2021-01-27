import irc.client_aio
import json
from urllib.parse import urlparse, quote

class AioIRCCat(irc.client_aio.AioSimpleIRCClient):
	def __init__(self, targets, all_wikis):
		irc.client.SimpleIRCClient.__init__(self)
		self.targets = targets
		self.updated = []  # Storage for edited wikis
		self.updated_discussions = []
		self.wikis = all_wikis

	def on_welcome(self, connection, event):  # Join IRC channels
		for channel in self.targets.values():
			connection.join(channel)

	def on_pubmsg(self, channel, event):
		if channel == self.targets["rc"]:
			self.parse_fandom_message(' '.join(event.arguments))
		elif channel == self.targets["discussion"]:
			self.parse_fandom_discussion(' '.join(event.arguments))

	def on_nicknameinuse(self, c, e):
		c.nick(c.get_nickname() + "_")

	def parse_fandom_message(self, message):
		message = message.split("\x035*\x03")
		# print(asyncio.all_tasks())
		half = message[0].find("\x0302http")
		if half == -1:
			return
		message = message[0][half + 3:].strip()
		# print(message)
		url = urlparse(message)
		full_url = url.netloc + recognize_langs(url.path)
		if full_url in self.wikis:
			self.updated.append(full_url)

	def parse_discussions_message(self, message):
		post = json.loads(message)
		if post.get('action', 'unknown') != "deleted":  # ignore deletion events
			url = urlparse(post.get('url'))
			full_url = url.netloc + recognize_langs(url.path)
			self.updated_discussions.append(full_url)


def recognize_langs(path):
	lang = ""
	new_path = path.split("/")
	if len(new_path)>2:
		if new_path[1] != "wiki":
			lang = "/"+new_path[1]
	return lang


