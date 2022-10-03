# This file is part of Recent changes Goat compatible Discord webhook (RcGcDw).

# RcGcDw is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# RcGcDw is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with RcGcDw.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import annotations
import json
import math
import random
from collections import defaultdict

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
	from wiki import Wiki

with open("src/api/template_settings.json", "r") as template_json:
	settings: dict = json.load(template_json)


class DiscordMessageMetadata:
	def __init__(self, method, log_id = None, page_id = None, rev_id = None, webhook_url = None):
		self.method = method  # unused, remains for compatibility reasons
		self.page_id = page_id
		self.log_id = log_id
		self.rev_id = rev_id
		self.webhook_url = webhook_url

	def matches(self, other: dict):
		for key, value in other.items():
			if self.__dict__[key] != value:
				return False
			return True

	def dump_ids(self) -> (int, int, int):
		return self.page_id, self.rev_id, self.log_id


class DiscordMessage:
	"""A class defining a typical Discord JSON representation of webhook payload."""
	def __init__(self, message_type: str, event_type: str, webhook_url: list[str], content=None):
		self.webhook_object = dict(allowed_mentions={"parse": []})
		self.length = 0
		self.metadata: Optional[DiscordMessageMetadata] = None
		self.wiki: Optional[Wiki] = None

		if message_type == "embed":
			self.__setup_embed()
		elif message_type == "compact":
			if settings["event_appearance"].get(event_type, {"emoji": None})["emoji"]:
				content = settings["event_appearance"][event_type]["emoji"] + " " + content
			self.webhook_object["content"] = content
			self.length = len(content)

		self.message_type = message_type
		self.event_type = event_type

	def __setitem__(self, key, value):
		"""Set item is used only in embeds."""
		try:
			if key in ('title', 'description'):
				self.length += len(value) - len(self.embed.get(key, ""))
			self.embed[key] = value
		except NameError:
			raise TypeError("Tried to assign a value when message type is plain message!")

	def __getitem__(self, item):
		return self.embed[item]

	def __repr__(self):
		"""Return the Discord webhook object ready to be sent"""
		return json.dumps(self.webhook_object)

	def __len__(self):
		return self.length

	def matches(self, other: dict):
		return self.metadata.matches(other)

	def message_type(self):
		if "content" in self.webhook_object:
			return "compact"
		return "embed"

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
		if self.message_type != "embed":
			return
		if self.embed["color"] is None:
			if settings["event_appearance"].get(self.event_type, {"color": None})["color"] is None:
				self.embed["color"] = random.randrange(1, 16777215)
			else:
				self.embed["color"] = settings["event_appearance"][self.event_type]["color"]
		else:
			self.embed["color"] = math.floor(self.embed["color"])
		if not self.embed["author"].get("icon_url", None) and settings["event_appearance"].get(self.event_type, {"icon": None})["icon"]:
			self.embed["author"]["icon_url"] = settings["event_appearance"][self.event_type]["icon"]
		if len(self.embed["title"]) > 254:
			self.embed["title"] = self.embed["title"][0:253] + "…"
		self.finish_embed_message()

	def finish_embed_message(self):
		if "embeds" not in self.webhook_object:
			self.webhook_object["embeds"] = [self.embed]
		else:
			if len(self.webhook_object["embeds"]) > 9:
				raise EmbedListFull
			self.webhook_object["embeds"].append(self.embed)

	def set_author(self, name: str, url="", icon_url=""):
		self.length += len(name)
		self.embed["author"]["name"] = name
		self.embed["author"]["url"] = url
		self.embed["author"]["icon_url"] = icon_url

	def set_footer(self, text: str, icon_url=""):
		self.length += len(text)
		self.embed["footer"]["text"] = text
		self.embed["footer"]["icon_url"] = icon_url

	def add_field(self, name, value, inline=False):
		if "fields" not in self.embed:
			self.embed["fields"] = []
		self.length += len(name) + len(value)
		self.embed["fields"].append(dict(name=name, value=value, inline=inline))

	def set_avatar(self, url):
		self.webhook_object["avatar_url"] = url

	def set_name(self, name):
		self.webhook_object["username"] = name

	def set_link(self, link):
		self.embed["link"] = link

	def return_content(self):
		return self.webhook_object["content"]


class DiscordMessageRaw(DiscordMessage):
	def __init__(self, content: dict, webhook_url: str):
		self.webhook_object = content
		self.webhook_url = webhook_url


class MessageTooBig(BaseException):
	pass


class StackedDiscordMessage():
	def __init__(self, m_type: int, wiki: Wiki):
		self.message_list: list[DiscordMessage] = []
		self.length = 0
		self.message_type: int = m_type  # 0 for compact, 1 for embed
		self.discord_callback_message_id: int = -1
		self.wiki: Wiki = wiki
		self.webhook: Optional[str] = None

	def __len__(self):
		return self.length

	def __repr__(self):
		message_structure = dict(allowed_mentions={"parse": []})
		if self.message_type == 0:
			message_structure["content"] = "\n".join([message.return_content() for message in self.message_list])
		elif self.message_type == 1:
			message_structure["embeds"] = [message["embeds"][0] for message in self.message_list]
		return json.dumps(message_structure)

	def filter(self, params: dict) -> list[tuple[int, DiscordMessage]]:
		"""Filters messages by their metadata"""
		return [(num, message) for num, message in enumerate(self.message_list) if message.matches(params)]

	def delete_message_by_id(self, message_ids: list[int]):
		"""Deletes messages with given IDS from the message_ids list"""
		for message_id in sorted(message_ids, reverse=True):
			self.message_list.pop(message_id)

	def add_message(self, message: DiscordMessage):
		if len(self) + len(message) > 6000 or len(self.message_list) > 9:
			raise MessageTooBig
		self.length += len(message)
		self.message_list.append(message)
		# self._setup_embed()
		# self.embed = message.embed
		# self.finish_embed_message()