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
import sys
import time
import logging
import asyncio
from src.config import settings
from src.discord.message import StackedDiscordMessage, MessageTooBig
from typing import Optional, Union, Tuple, AsyncGenerator
from collections import defaultdict

from src.discord.message import DiscordMessage, DiscordMessageMetadata, DiscordMessageRaw

AUTO_SUPPRESSION_ENABLED = settings.get("auto_suppression", {"enabled": False}).get("enabled")
if AUTO_SUPPRESSION_ENABLED:
	from src.fileio.database import add_entry as add_message_redaction_entry

rate_limit = 0

logger = logging.getLogger("rcgcdw.discord.queue")

class QueueEntry:
	def __init__(self, discord_message, webhooks):
		self.discord_message: DiscordMessage = discord_message
		self.webhooks: list[str] = webhooks
		self._sent_webhooks: set[str] = set()

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

	async def pack_massages(self, messages: list[QueueEntry]) -> AsyncGenerator[tuple[StackedDiscordMessage, int]]:
		"""Pack messages into StackedDiscordMessage. It's an async generator"""
		current_pack = StackedDiscordMessage(0 if messages[0].discord_message.message_type == "compact" else 1)  # first message
		index = -1
		for index, message in enumerate(messages):
			message = message.discord_message
			try:
				current_pack.add_message(message)
			except MessageTooBig:
				yield current_pack
				current_pack = StackedDiscordMessage(0 if message.message_type == "compact" else 1)  # next messages
				current_pack.add_message(message)
		yield current_pack, index

	async def send_msg_set(self, msg_set: tuple[str, list[QueueEntry]]):
		webhook_url, messages = msg_set  # str("daosdkosakda/adkahfwegr34", list(DiscordMessage, DiscordMessage, DiscordMessage)
		async for msg, index in self.pack_massages(messages):
			if self.global_rate_limit:
				return  # if we are globally rate limited just wait for first gblocked request to finish
			# Verify that message hasn't been sent before
			status = await send_to_discord_webhook(msg, webhook_url)
			if status[0] < 2:
				logger.debug("Sending message succeeded")
				for queue_message in messages[max(index-10, 0):index]:  # mark messages as delivered
					queue_message.confirm_sent_status(webhook_url)
				logger.debug("Current rate limit time: {}".format(status[1]))
				if status[1] is not None:
					await asyncio.sleep(float(status[1]))  # note, the timer on the last request won't matter that much since it's separate task and for the time of sleep it will give control to other tasks
					break
			elif status[0] == 5:
				if status[1]["global"] is True:
					logger.debug(
						"Global rate limit has been detected. Setting global_rate_limit to true and awaiting punishment.")
					self.global_rate_limit = True
				await asyncio.sleep(status[1]["retry_after"] / 1000)
				break
			else:
				logger.debug("Sending message failed")
				break

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


def handle_discord_http(code, formatted_embed, result):
	if 300 > code > 199:  # message went through
		return 0
	elif code == 400:  # HTTP BAD REQUEST result.status_code, data, result, header
		logger.error(
			"Following message has been rejected by Discord, please submit a bug on our bugtracker adding it:")
		logger.error(formatted_embed)
		logger.error(result.text)
		return 1
	elif code == 401 or code == 404:  # HTTP UNAUTHORIZED AND NOT FOUND
		if result.request.method == "POST":  # Ignore not found for DELETE and PATCH requests since the message could already be removed by admin
			logger.error("Webhook URL is invalid or no longer in use, please replace it with proper one.")
			remove_webhook_maybe()
		else:
			return 0
	elif code == 429:
		logger.error("We are sending too many requests to the Discord, slowing down...")
		return 2
	elif 499 < code < 600:
		logger.error(
			"Discord have trouble processing the event, and because the HTTP code returned is {} it means we blame them.".format(
				code))
		return 3
	else:
		logger.error("There was an unexpected HTTP code returned from Discord: {}".format(code))
		return 1


def send_to_discord_webhook(message: [StackedDiscordMessage, DiscordMessage]):
	header = settings["header"]
	header['Content-Type'] = 'application/json'
	standard_args = dict(headers=header)
	if isinstance(message, StackedDiscordMessage):
		req =
	else:
		message.metadata.method
	if metadata.method == "POST":
		req = requests.Request("POST", data.webhook_url+"?wait=" + ("true" if AUTO_SUPPRESSION_ENABLED else "false"), data=repr(data), **standard_args)
	elif metadata.method == "DELETE":
		req = requests.Request("DELETE", metadata.webhook_url, **standard_args)
	elif metadata.method == "PATCH":
		req = requests.Request("PATCH", data.webhook_url, data=repr(data), **standard_args)
	try:
		time.sleep(rate_limit)
		rate_limit = 0
		req = req.prepare()
		result = requests.Session().send(req, timeout=10)
		update_ratelimit(result)
		if AUTO_SUPPRESSION_ENABLED and metadata.method == "POST":
			if 199 < result.status_code < 300:  # check if positive error log
				try:
					add_message_redaction_entry(*metadata.dump_ids(), repr(data), result.json().get("id"))
				except ValueError:
					logger.error("Couldn't get json of result of sending Discord message.")
			else:
				pass
	except requests.exceptions.Timeout:
		logger.warning("Timeouted while sending data to the webhook.")
		return 3
	except requests.exceptions.ConnectionError:
		logger.warning("Connection error while sending the data to a webhook")
		return 3
	else:
		return handle_discord_http(result.status_code, data, result)


def send_to_discord(data: Optional[DiscordMessage], meta: DiscordMessageMetadata):
	if data is not None:
		for regex in settings["disallow_regexes"]:
			if data.webhook_object.get("content", None):
				if re.search(re.compile(regex), data.webhook_object["content"]):
					logger.info("Message {} has been rejected due to matching filter ({}).".format(data.webhook_object["content"], regex))
					return  # discard the message without anything
			else:
				for to_check in [data.webhook_object.get("description", ""), data.webhook_object.get("title", ""), *[x["value"] for x in data["fields"]], data.webhook_object.get("author", {"name": ""}).get("name", "")]:
					if re.search(re.compile(regex), to_check):
						logger.info("Message \"{}\" has been rejected due to matching filter ({}).".format(
							to_check, regex))
						return  # discard the message without anything
	if messagequeue:
		messagequeue.add_message((data, meta))
	else:
		code = send_to_discord_webhook(data, metadata=meta)
		if code == 3:
			messagequeue.add_message((data, meta))
		elif code == 2:
			time.sleep(5.0)
			messagequeue.add_message((data, meta))
		elif code is None or code < 2:
			pass