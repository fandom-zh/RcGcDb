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

import re
import time
import logging
import asyncio

import aiohttp
from aiohttp import ContentTypeError, ClientResponse

from src.exceptions import ExhaustedDiscordBucket
from src.config import settings
from src.discord.message import StackedDiscordMessage, MessageTooBig
from typing import Optional, AsyncGenerator, TYPE_CHECKING
from collections import defaultdict

from src.discord.message import DiscordMessage, DiscordMessageMetadata

if TYPE_CHECKING:
	from src.wiki import Wiki

rate_limit = 0

logger = logging.getLogger("rcgcdb.discord.queue")


class QueueEntry:
	def __init__(self, discord_message, webhooks, wiki, method="POST"):
		self.discord_message: [DiscordMessage, StackedDiscordMessage] = discord_message
		self.webhooks: list[str] = webhooks
		self._sent_webhooks: set[str] = set()
		self.wiki: Wiki = wiki
		self.method = method

	def check_sent_status(self, webhook: str) -> bool:
		"""Checks sent status for given message, if True it means that the message has been sent before to given webhook, otherwise False."""
		return webhook in self._sent_webhooks

	def confirm_sent_status(self, webhook: str):
		"""Confirms sent status for a webhook. Returns True if sending to all webhooks has been completed, otherwise False."""
		self._sent_webhooks.add(webhook)

	def complete(self) -> bool:
		return len(self._sent_webhooks) == len(self.webhooks)

	def __iter__(self):
		return iter(self.webhooks)


class MessageQueue:
	"""Message queue class for undelivered messages"""
	def __init__(self):
		self._queue: list[QueueEntry] = []

	def __repr__(self):
		return self._queue

	def __len__(self):
		return len(self._queue)

	def __iter__(self):
		return iter(self._queue)

	def clear(self):
		self._queue.clear()

	def add_messages(self, messages: list[QueueEntry]):
		for message in messages:
			self.add_message(message)

	def add_message(self, message: QueueEntry):
		self._queue.append(message)

	def cut_messages(self, item_num: int):
		self._queue = self._queue[item_num:]

	@staticmethod
	def compare_message_to_dict(metadata: DiscordMessageMetadata, to_match: dict):
		"""Compare DiscordMessageMetadata fields and match them against dictionary"""
		for name, val in to_match.items():
			if getattr(metadata, name, None) != val:
				return False
		return True

	async def group_by_webhook(self):
		"""Group Discord messages in the queue by the dictionary, allowing to send multiple messages to different
		webhooks at the same time avoiding ratelimits per Discord webhook route."""
		message_dict = defaultdict(list)
		for msg in self._queue:
			if not isinstance(msg.webhooks, list):
				raise TypeError('msg.webhook_url in _queue is not a list')
			for webhook in msg.webhooks:
				message_dict[webhook].append(msg)  # defaultdict{"dadibadyvbdmadgqueh23/dihjd8agdandashd": [DiscordMessage, DiscordMessage]}
		return message_dict.items()

	def delete_all_with_matching_metadata(self, **properties):
		"""Deletes all of the messages that have matching metadata properties (useful for message redaction)"""
		for index, item in reversed(list(enumerate(self._queue))):
			if self.compare_message_to_dict(item[1], properties):
				self._queue.pop(index)

	async def pack_massages(self, messages: list[QueueEntry], current_pack=None) -> AsyncGenerator[tuple[StackedDiscordMessage, int, str], None]:
		"""Pack messages into StackedDiscordMessage. It's an async generator"""
		for index, message in enumerate(messages):
			if message.method == "POST":
				if current_pack is None:
					current_pack = StackedDiscordMessage(0 if message.discord_message.message_type == "compact" else 1,
													 message.wiki)
			else:
				yield message.discord_message, index, message.method
			discord_message = message.discord_message
			try:
				current_pack.add_message(discord_message)
			except MessageTooBig:
				yield current_pack, index-1, "POST"
				current_pack = StackedDiscordMessage(0 if discord_message.message_type == "compact" else 1, message.wiki)  # next messages
				current_pack.add_message(discord_message)
		yield current_pack, index, "POST"

	async def send_msg_set(self, msg_set: tuple[str, list[QueueEntry]]):
		webhook_url, messages = msg_set  # str("daosdkosakda/adkahfwegr34", list(DiscordMessage, DiscordMessage, DiscordMessage)
		async for msg, index, method in self.pack_massages(messages):
			client_error = False
			if self.global_rate_limit:
				return  # if we are globally rate limited just wait for first gblocked request to finish
			# Verify that message hasn't been sent before
			# noinspection PyTypeChecker
			try:
				status = await send_to_discord_webhook(msg, webhook_url, method)
			except aiohttp.ClientError:
				client_error = True
			except (aiohttp.ServerConnectionError, aiohttp.ServerTimeoutError):
				# Retry on next Discord message sent attempt
				return
			except ExhaustedDiscordBucket as e:
				if e.is_global:
					self.global_rate_limit = True
				await asyncio.sleep(e.remaining / 1000)
				return
			for queue_message in messages[max(index-len(msg.message_list), 0):index+1]:  # mark messages as delivered
				queue_message.confirm_sent_status(webhook_url)
			if client_error is False:
				msg.webhook = webhook_url
				msg.wiki.add_message(msg)

	async def resend_msgs(self):
		self.global_rate_limit = False
		if self._queue:
			logger.info(
				"{} messages waiting to be delivered to Discord.".format(len(self._queue)))
			tasks_to_run = []
			for set_msgs in await self.group_by_webhook():
				# logger.debug(set_msgs)
				tasks_to_run.append(self.send_msg_set(set_msgs))
			await asyncio.gather(*tasks_to_run)  # we wait for all send_msg_set functions to finish
			self._queue = [x for x in self._queue if x.complete() is False]  # get rid of sent messages
		else:
			await asyncio.sleep(0.5)


messagequeue = MessageQueue()


async def handle_discord_http(code: int, formatted_embed: str, result: ClientResponse):
	text = await result.text()
	print("HTTP response is {} and response {}".format(code, text))
	if 300 > code > 199:  # message went through
		return 0
	elif code == 400:  # HTTP BAD REQUEST result.status_code, data, result, header
		logger.error(
			"Following message has been rejected by Discord, please submit a bug on our bugtracker adding it:")
		logger.error(formatted_embed)
		logger.error(text)
		raise aiohttp.ClientError("Message rejected.")
	elif code == 401 or code == 404:  # HTTP UNAUTHORIZED AND NOT FOUND
		if result.method == "POST":  # Ignore not found for DELETE and PATCH requests since the message could already be removed by admin
			logger.error("Webhook URL is invalid or no longer in use, please replace it with proper one.")
			# TODO remove_webhook_maybe()
			raise aiohttp.ClientError("Message sent to bad webhook.")
		else:
			return 0
	elif code == 429:
		logger.error("We are sending too many requests to the Discord, slowing down...")
		if "x-ratelimit-global" in result.headers.keys():
			raise ExhaustedDiscordBucket(remaining=int(result.headers.get("x-ratelimit-reset-after")), is_global=True)
		raise ExhaustedDiscordBucket(remaining=int(result.headers.get("x-ratelimit-reset-after")), is_global=False)
	elif 499 < code < 600:
		logger.error(
			"Discord have trouble processing the event, and because the HTTP code returned is {} it means we blame them.".format(
				code))
		raise aiohttp.ServerConnectionError()
	else:
		logger.error("There was an unexpected HTTP code returned from Discord: {}".format(code))
		raise aiohttp.ServerConnectionError()


async def send_to_discord_webhook(message: [StackedDiscordMessage, DiscordMessageMetadata], webhook_path: str, method: str):
	logger.debug("We are at sent_to_discord for {}".format(message))
	header = settings["header"]
	header['Content-Type'] = 'application/json'
	header['X-RateLimit-Precision'] = "millisecond"
	async with aiohttp.ClientSession(headers=header, timeout=aiohttp.ClientTimeout(total=6)) as session:
		if isinstance(message, StackedDiscordMessage):
			async with session.post(f"https://discord.com/api/webhooks/{webhook_path}?wait=true", data=repr(message)) as resp:  # TODO Detect Invalid Webhook Token
				try:
					resp_json = await resp.json()
					# Add Discord Message ID which we can later use to delete/redact messages if we want
					message.discord_callback_message_id = resp_json["id"]
				except KeyError:
					raise aiohttp.ServerConnectionError(f"Could not get the ID from POST request with message data. Data: {await resp.text()}")
				except ContentTypeError:
					logger.exception("Could not receive message ID from Discord due to invalid MIME type of response.")
				except ValueError:
					logger.exception(f"Could not decode JSON response from Discord. Response: {await resp.text()}]")
				return await handle_discord_http(resp.status, repr(message), resp)
		elif method == "DELETE":
			async with session.request(method=message.method, url=f"https://discord.com/api/webhooks/{webhook_path}/messages/{message.discord_callback_message_id}") as resp:
				return await handle_discord_http(resp.status, repr(message), resp)
		elif method == "PATCH":
			async with session.request(method=message.method, url=f"https://discord.com/api/webhooks/{webhook_path}/messages/{message.discord_callback_message_id}", data=repr(message)) as resp:
				return await handle_discord_http(resp.status, repr(message), resp)
