import json, random, math, logging
from collections import defaultdict

from src.misc import logger
from src.config import settings
from src.database import db
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
	async with db.pool().acquire() as connection:
		async with connection.transaction():
			async for observer in connection.cursor('SELECT webhook, lang FROM rcgcdw WHERE wiki = $1', wiki_url):
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


def stack_message_list(messages: list) -> list:
	if len(messages) > 1:
		if messages[0].message_type() == "embed":
			# for i, msg in enumerate(messages):
			# 	if not isinstance(msg, StackedDiscordMessage):
			# 		break
			# else:  # all messages in messages are stacked, exit this if
			# 	i += 1
			removed_msgs = 0
			# We split messages into groups of 10
			for group_index in range(ceil((len(messages)) / 10)):
				message_group_index = group_index * 10 - removed_msgs  # this helps us with calculations which messages we need
				stackable = StackedDiscordMessage(messages[message_group_index])  # treat the first message from the group as main
				for message in messages[message_group_index + 1:message_group_index + 10]:  # we grab messages from messages list
					try:
						stackable.add_embed(message)  # and to our main message we add ones after it that are from same group
					except EmbedListFull:  # if there are too many messages in our group we simply break so another group can be made
						break
					messages.remove(message)
					removed_msgs += 1  # helps with calculating message_group_index
				messages[message_group_index] = stackable
		elif messages[0].message_type() == "compact":
			message_index = 0
			while len(messages) > message_index+1:  # as long as we have messages to stack
				if (len(messages[message_index]) + len(messages[message_index+1])) < 2000:  # if overall length is lower than 2000
					messages[message_index].webhook_object["content"] = messages[message_index].webhook_object["content"] + "\n" + messages[message_index + 1].webhook_object["content"]
					messages[message_index].length += (len(messages[message_index + 1]) + 1)
					messages.remove(messages[message_index + 1])
				else:
					message_index += 1
	return messages





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
		async with db.pool().acquire() as connection:
			await connection.execute("DELETE FROM rcgcdw WHERE webhook = $1", webhook_url)
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


class DiscordMessageMetadata:
	def __init__(self, method, log_id = None, page_id = None, rev_id = None, webhook_url = None, new_data = None):
		self.method = method
		self.page_id = page_id
		self.log_id = log_id
		self.rev_id = rev_id
		self.webhook_url = webhook_url
		self.new_data = new_data

	def dump_ids(self) -> (int, int, int):
		return self.page_id, self.rev_id, self.log_id
