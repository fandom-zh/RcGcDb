import json, random, math, logging
from collections import defaultdict
from src.config import settings
from src.database import db_cursor

logger = logging.getLogger("rcgcdb.discord")

# General functions
class DiscordMessage():
	"""A class defining a typical Discord JSON representation of webhook payload."""
	def __init__(self, message_type: str, event_type: str, webhook_url: str, content=None):
		self.webhook_object = dict(allowed_mentions={"parse": []})
		self.webhook_url = webhook_url

		if message_type == "embed":
			self.__setup_embed()
		elif message_type == "compact":
			self.webhook_object["content"] = content

		self.event_type = event_type

	def __setitem__(self, key, value):
		"""Set item is used only in embeds."""
		try:
			self.embed[key] = value
		except NameError:
			raise TypeError("Tried to assign a value when message type is plain message!")

	def __getitem__(self, item):
		return self.embed[item]

	def __repr__(self):
		"""Return the Discord webhook object ready to be sent"""
		return json.dumps(self.webhook_object)

	def __setup_embed(self):
		self.embed = defaultdict(dict)
		if "embeds" not in self.webhook_object:
			self.webhook_object["embeds"] = [self.embed]
		else:
			self.webhook_object["embeds"].append(self.embed)
		self.embed["color"] = None

	def add_embed(self):
		self.finish_embed()
		self.__setup_embed()

	def finish_embed(self):
		if self.embed["color"] is None:
			self.embed["color"] = random.randrange(1, 16777215)
		else:
			self.embed["color"] = math.floor(self.embed["color"])

	def set_author(self, name, url, icon_url=""):
		self.embed["author"]["name"] = name
		self.embed["author"]["url"] = url
		self.embed["author"]["icon_url"] = icon_url

	def add_field(self, name, value, inline=False):
		if "fields" not in self.embed:
			self.embed["fields"] = []
		self.embed["fields"].append(dict(name=name, value=value, inline=inline))

	def set_avatar(self, url):
		self.webhook_object["avatar_url"] = url

	def set_name(self, name):
		self.webhook_object["username"] = name


# User facing webhook functions
def wiki_removal(wiki_id, status):  # TODO Add lang selector
	reasons = {410: _("wiki deletion"), 404: _("wiki deletion"), 401: _("wiki becoming inaccessible"),
	           402: _("wiki becoming inaccessible"), 403: _("wiki becoming inaccessible")}
	reason = reasons.get(status, _("unknown error"))
	for observer in db_cursor.execute('SELECT * FROM observers WHERE wiki_id = ?', wiki_id):
		DiscordMessage("compact", "webhook/remove", webhook_url=observer[4], content=_("The webhook for {} has been removed due to {}.".format(reason)))  # TODO

# Monitoring webhook functions
def wiki_removal_monitor(wiki_id, status):
	pass