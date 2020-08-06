import json, random, math, logging
from collections import defaultdict

from src.misc import logger
from src.config import settings
from src.database import db_cursor
from src.i18n import langs
from asyncio import TimeoutError

import aiohttp

logger = logging.getLogger("rcgcdb.discord")

# General functions

default_header = settings["header"]
default_header['Content-Type'] = 'application/json'
default_header["X-RateLimit-Precision"] = "millisecond"


# User facing webhook functions
async def wiki_removal(wiki_url, status):
	for observer in db_cursor.execute('SELECT webhook, lang FROM rcgcdw WHERE wiki = ?', (wiki_url,)):
		def _(string: str) -> str:
			"""Our own translation string to make it compatible with async"""
			return langs[observer["lang"]].gettext(string)
		reasons = {410: _("wiki deletion"), 404: _("wiki deletion"), 401: _("wiki becoming inaccessible"),
		           402: _("wiki becoming inaccessible"), 403: _("wiki becoming inaccessible")}
		reason = reasons.get(status, _("unknown error"))
		await send_to_discord_webhook(DiscordMessage("compact", "webhook/remove", webhook_url=[], content=_("The webhook for {} has been removed due to {}.".format(wiki_url, reason)), wiki=None), webhook_url=observer["webhook"])
		header = settings["header"]
		header['Content-Type'] = 'application/json'
		header['X-Audit-Log-Reason'] = "Wiki becoming unavailable"
		async with aiohttp.ClientSession(headers=header, timeout=aiohttp.ClientTimeout(5.0)) as session:
			await session.delete("https://discord.com/api/webhooks/"+observer["webhook"])


async def webhook_removal_monitor(webhook_url: list, reason: int):
	await send_to_discord_webhook_monitoring(DiscordMessage("compact", "webhook/remove", None, content="The webhook {} has been removed due to {}.".format("https://discord.com/api/webhooks/" + webhook_url[0], reason), wiki=None))


class DiscordMessage:
	"""A class defining a typical Discord JSON representation of webhook payload."""
	def __init__(self, message_type: str, event_type: str, webhook_url: list, wiki, content=None):
		self.webhook_object = dict(allowed_mentions={"parse": []})
		self.webhook_url = webhook_url
		self.wiki = wiki

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
			if settings["appearance"]["embed"].get(self.event_type, {"color": None})["color"] is None:
				self.embed["color"] = random.randrange(1, 16777215)
			else:
				self.embed["color"] = settings["appearance"]["embed"][self.event_type]["color"]
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


# Monitoring webhook functions
async def wiki_removal_monitor(wiki_url, status):
	await send_to_discord_webhook_monitoring(DiscordMessage("compact", "webhook/remove", content="Removing {} because {}.".format(wiki_url, status), webhook_url=[None], wiki=None))


async def discussion_task_exception_logger(wiki, exception):
	message = DiscordMessage("embed", "bot/exception", [None], wiki=None)
	message["description"] = exception
	message["title"] = "Discussion task exception logger"
	message.add_field("Wiki", wiki)
	message.finish_embed()
	await send_to_discord_webhook_monitoring(message)


async def group_task_exception_logger(group, exception):
	message = DiscordMessage("embed", "bot/exception", [None], wiki=None)
	message["description"] = exception
	message["title"] = "Group task exception logger"
	message.add_field("Group", group)
	message.finish_embed()
	await send_to_discord_webhook_monitoring(message)


async def formatter_exception_logger(wiki_url, change, exception):
	"""Creates a Discord message reporting a crash in RC formatter area"""
	message = DiscordMessage("embed", "bot/exception", [None], wiki=None)
	message["description"] = exception
	message["title"] = "RC Exception Report"
	change = str(change)[0:1000]
	message.add_field("Wiki URL", wiki_url)
	message.add_field("Change", change)
	message.finish_embed()
	await send_to_discord_webhook_monitoring(message)


async def msg_sender_exception_logger(exception):
	"""Creates a Discord message reporting a crash in RC formatter area"""
	message = DiscordMessage("embed", "bot/exception", [None], wiki=None)
	message["description"] = exception
	message["title"] = "MSGSENDER Exception Report"
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
		status = await handle_discord_http(result.status, repr(data), result, data)
		if status == 5:
			return 5, await result.json()
		else:
			return status, rate_limit


async def handle_discord_http(code: int, formatted_embed: str, result: aiohttp.ClientResponse, dmsg: DiscordMessage):
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
		db_cursor.execute("DELETE FROM rcgcdw WHERE webhook = ?", (dmsg.webhook_url[0],))
		await webhook_removal_monitor(dmsg.webhook_url, code)
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
