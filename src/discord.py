import json, random, math, logging
from collections import defaultdict

from src.misc import logger
from src.config import settings
from src.database import db_cursor
from src.i18n import langs
from src.exceptions import EmbedListFull
from asyncio import TimeoutError
from math import ceil

import aiohttp

logger = logging.getLogger("rcgcdb.discord")

# General functions

default_header = settings["header"]
default_header['Content-Type'] = 'application/json'
default_header["X-RateLimit-Precision"] = "millisecond"


# User facing webhook functions
async def wiki_removal(wiki_url, status):
	for observer in db_cursor.execute('SELECT webhook, lang FROM rcgcdw WHERE wiki = ?', (wiki_url,)):
		_ = langs[observer["lang"]]["discord"].gettext
		reasons = {410: _("wiki deleted"), 404: _("wiki deleted"), 401: _("wiki inaccessible"),
		           402: _("wiki inaccessible"), 403: _("wiki inaccessible"), 1000: _("discussions disabled")}
		reason = reasons.get(status, _("unknown error"))
		await send_to_discord_webhook(DiscordMessage("compact", "webhook/remove", webhook_url=[], content=_("This recent changes webhook has been removed for `{reason}`!").format(reason=reason), wiki=None), webhook_url=observer["webhook"])
		header = settings["header"]
		header['Content-Type'] = 'application/json'
		header['X-Audit-Log-Reason'] = "Wiki becoming unavailable"
		async with aiohttp.ClientSession(headers=header, timeout=aiohttp.ClientTimeout(5.0)) as session:
			await session.delete("https://discord.com/api/webhooks/"+observer["webhook"])


async def webhook_removal_monitor(webhook_url: str, reason: int):
	await send_to_discord_webhook_monitoring(DiscordMessage("compact", "webhook/remove", None, content="The webhook {} has been removed due to {}.".format("https://discord.com/api/webhooks/" + webhook_url, reason), wiki=None))


class DiscordMessage:
	"""A class defining a typical Discord JSON representation of webhook payload."""
	def __init__(self, message_type: str, event_type: str, webhook_url: list, wiki, content=None):
		self.webhook_object = dict(allowed_mentions={"parse": []})
		self.webhook_url = webhook_url
		self.wiki = wiki
		self.length = 0

		if message_type == "embed":
			self._setup_embed()
		elif message_type == "compact":
			self.webhook_object["content"] = content
			self.length = len(content)

		self.event_type = event_type

	def message_type(self):
		if "content" in self.webhook_object:
			return "compact"
		return "embed"

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

	def _setup_embed(self):
		"""Setup another embed"""
		self.embed = defaultdict(dict)
		self.embed["color"] = None

	def __len__(self):
		return self.length

	def finish_embed(self):
		if self.embed["color"] is None:
			if settings["appearance"]["embed"].get(self.event_type, {"color": None})["color"] is None:
				self.embed["color"] = random.randrange(1, 16777215)
			else:
				self.embed["color"] = settings["appearance"]["embed"][self.event_type]["color"]
		else:
			self.embed["color"] = math.floor(self.embed["color"])
		if "embeds" not in self.webhook_object:
			self.webhook_object["embeds"] = [self.embed]
		else:
			if len(self.webhook_object["embeds"]) > 9:
				raise EmbedListFull
			self.webhook_object["embeds"].append(self.embed)

	def set_author(self, name: str, url: str, icon_url=""):
		self.length += len(name)
		self.embed["author"]["name"] = name
		self.embed["author"]["url"] = url
		self.embed["author"]["icon_url"] = icon_url

	def add_field(self, name, value, inline=False):
		if "fields" not in self.embed:
			self.embed["fields"] = []
		self.length += len(name) + len(value)
		self.embed["fields"].append(dict(name=name, value=value, inline=inline))

	def set_avatar(self, url):
		self.webhook_object["avatar_url"] = url

	def set_name(self, name):
		self.webhook_object["username"] = name

def stack_message_list(messages: list) -> list:
	if len(messages) > 1:
		if messages[0].message_type() == "embed":
			# for i, msg in enumerate(messages):
			# 	if not isinstance(msg, StackedDiscordMessage):
			# 		break
			# else:  # all messages in messages are stacked, exit this if
			# 	i += 1
			removed_msgs = 0
			for group_index in range(ceil((len(messages)) / 10)):
				message_group_index = group_index * 10 - removed_msgs
				stackable = StackedDiscordMessage(messages[message_group_index])
				for message in messages[message_group_index + 1:message_group_index + 10]:
					try:
						stackable.add_embed(message.embed)
					except EmbedListFull:
						break
					messages.remove(message)
					removed_msgs += 1
				messages[message_group_index] = stackable
		elif messages[0].message_type() == "compact":
			message_index = 0
			while len(messages) > message_index+1:
				if (len(messages[message_index]) + len(messages[message_index+1])) < 2000:
					messages[message_index].webhook_object["content"] = messages[message_index].webhook_object["content"] + "\n" + messages[message_index + 1].webhook_object["content"]
					messages[message_index].length += (len(messages[message_index + 1]) + 1)
					messages.remove(messages[message_index + 1])
				else:
					message_index += 1
	return messages


class StackedDiscordMessage(DiscordMessage):
	def __init__(self, discordmessage: DiscordMessage):
		if isinstance(discordmessage, StackedDiscordMessage):
			raise TypeError("Cannot transform StackedDiscordMessage")
		self.__dict__ = discordmessage.__dict__

	def stack(self, messages: list):
		for message in messages:
			self.add_embed(message.embed)

	def add_embed(self, embed):
		if len(self) + len(embed) > 6000:
			raise EmbedListFull
		self._setup_embed()
		self.embed = embed
		self.finish_embed()


# Monitoring webhook functions
async def wiki_removal_monitor(wiki_url, status):
	await send_to_discord_webhook_monitoring(DiscordMessage("compact", "webhook/remove", content="Removing {} because {}.".format(wiki_url, status), webhook_url=[None], wiki=None))


async def generic_msg_sender_exception_logger(exception: str, title: str, **kwargs):
	"""Creates a Discord message reporting a crash"""
	message = DiscordMessage("embed", "bot/exception", [None], wiki=None)
	message["description"] = exception
	message["title"] = title
	for key, value in kwargs.items():
		message.add_field(key, value)
	message.finish_embed()
	await send_to_discord_webhook_monitoring(message)


async def send_to_discord_webhook_monitoring(data: DiscordMessage):
	header = settings["header"]
	header['Content-Type'] = 'application/json'
	async with aiohttp.ClientSession(headers=header, timeout=aiohttp.ClientTimeout(5.0)) as session:
		try:
			result = await session.post("https://discord.com/api/webhooks/"+settings["monitoring_webhook"], data=repr(data))
		except (aiohttp.ClientConnectionError, aiohttp.ServerConnectionError):
			logger.exception("Could not send the message to Discord")
			return 3


async def send_to_discord_webhook(data: DiscordMessage, webhook_url: str) -> tuple:
	"""Sends a message to webhook

	:return tuple(status code for request, rate limit info (None for can send more, string for amount of seconds to wait)"""
	async with aiohttp.ClientSession(headers=default_header, timeout=aiohttp.ClientTimeout(5.0)) as session:
		try:
			result = await session.post("https://discord.com/api/webhooks/"+webhook_url, data=repr(data))
			rate_limit = None if int(result.headers.get('x-ratelimit-remaining', "-1")) > 0 else result.headers.get('x-ratelimit-reset-after', None)
		except (aiohttp.ClientConnectionError, aiohttp.ServerConnectionError, TimeoutError):
			logger.exception("Could not send the message to Discord")
			return 3, None
		status = await handle_discord_http(result.status, repr(data), result, webhook_url)
		if status == 5:
			return 5, await result.json()
		else:
			return status, rate_limit


async def handle_discord_http(code: int, formatted_embed: str, result: aiohttp.ClientResponse, webhook_url: str):
	if 300 > code > 199:  # message went through
		return 0
	elif code == 400:  # HTTP BAD REQUEST result.status_code, data, result, header
		logger.error(
			"Following message has been rejected by Discord, please submit a bug on our bugtracker adding it:")
		logger.error(formatted_embed)
		logger.error(await result.text())
		return 1
	elif code == 401 or code == 404:  # HTTP UNAUTHORIZED AND NOT FOUND
		logger.error("Webhook URL is invalid or no longer in use, please replace it with proper one.")
		db_cursor.execute("DELETE FROM rcgcdw WHERE webhook = ?", (webhook_url,))
		await webhook_removal_monitor(webhook_url, code)
		return 1
	elif code == 429:
		logger.error("We are sending too many requests to the Discord, slowing down...")
		return 5
	elif 499 < code < 600:
		logger.error(
			"Discord have trouble processing the event, and because the HTTP code returned is {} it means we blame them.".format(
				code))
		return 3
	else:
		return 4
