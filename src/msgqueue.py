import asyncio, logging, aiohttp
import typing

from src.discord.message import DiscordMessage, StackedDiscordMessage, MessageTooBig
from src.config import settings
from src.exceptions import EmbedListFull
from collections import defaultdict
logger = logging.getLogger("rcgcdw.msgqueue")

class QueueEntry:
	def __init__(self, discord_message, webhooks):
		self.discord_message: DiscordMessage = discord_message
		self.webhooks: list[str] = webhooks

	def __iter__(self):
		return iter(self.webhooks)


class MessageQueue:
	"""Message queue class for undelivered messages"""
	def __init__(self):
		self._queue = []
		self.global_rate_limit = False

	def __repr__(self):
		return self._queue

	def __len__(self):
		return len(self._queue)

	def __iter__(self):
		return iter(self._queue)

	def clear(self):
		self._queue.clear()

	def add_messages(self, messages: list[QueueEntry]):
		self._queue.extend(messages)
		logger.debug("Adding new messages")
	#
	# def replace_message(self, to_replace: DiscordMessage, with_replace: StackedDiscordMessage):
	# 	try:
	# 		self._queue[self._queue.index(to_replace)] = with_replace
	# 	except ValueError:
	# 		raise

	def cut_messages(self, item_num):
		self._queue = self._queue[item_num:]

	async def group_by_webhook(self):  # TODO Change into iterable
		"""Group Discord messages in the queue by the dictionary, allowing to send multiple messages to different
		webhooks at the same time avoiding ratelimits per Discord webhook route."""
		message_dict = defaultdict(list)
		for msg in self._queue:
			if not isinstance(msg.webhook_url, list):
				raise TypeError('msg.webhook_url in _queue is not a list')
			for webhook in msg.webhook_url:
				message_dict[webhook].append(msg)  # defaultdict{"dadibadyvbdmadgqueh23/dihjd8agdandashd": [DiscordMessage, DiscordMessage]}
		return message_dict.items()  # dict_items([('daosdkosakda/adkahfwegr34', [DiscordMessage]), ('daosdkosakda/adkahfwegr33', [DiscordMessage, DiscordMessage])])

	async def pack_massages(self, messages: list[DiscordMessage]) -> typing.AsyncGenerator:
		"""Pack messages into StackedDiscordMessage. It's an async generator"""
		current_pack = StackedDiscordMessage(0 if messages[0].message_type == "compact" else 1)  # first message
		for message in messages:
			try:
				current_pack.add_message(message)
			except MessageTooBig:
				yield current_pack
				current_pack = StackedDiscordMessage(0 if message.message_type == "compact" else 1)  # next messages
				current_pack.add_message(message)
		yield current_pack

	async def send_msg_set(self, msg_set: tuple):
		webhook_url, messages = msg_set  #  str("daosdkosakda/adkahfwegr34", list(DiscordMessage, DiscordMessage, DiscordMessage)
		async for msg in self.pack_massages(messages):
			if self.global_rate_limit:
				return  # if we are globally rate limited just wait for first gblocked request to finish
			status = await send_to_discord_webhook(msg, webhook_url)
			if status[0] < 2:
				logger.debug("Sending message succeeded")
				try:
					if len(msg.webhook_url) > 1:
						msg.webhook_url.remove(webhook_url)
					else:
						self._queue.remove(msg)
				except ValueError:
					#  For the love of god I cannot figure why can it return ValueError: list.remove(x): x not in list, however considering it's not in the list, somehow, anymore we can just not care about it I guess
					pass
				logger.debug("Current rate limit time: {}".format(status[1]))
				if status[1] is not None:
					await asyncio.sleep(float(status[1]))  # note, the timer on the last request won't matter that much since it's separate task and for the time of sleep it will give control to other tasks
					break
			elif status[0] == 5:
				if status[1]["global"] is True:
					logger.debug("Global rate limit has been detected. Setting global_rate_limit to true and awaiting punishment.")
					self.global_rate_limit = True
				await asyncio.sleep(status[1]["retry_after"]/1000)
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
		else:
			await asyncio.sleep(0.5)


messagequeue = MessageQueue()


async def send_to_discord(msg):
	messagequeue.add_message(msg)
	# webhooks = msg.webhook_url.copy()
	# for webhook in webhooks:
	# 	msg.webhook_url = [webhook]  # Doing it just so it doesn't store reference but value
	# 	messagequeue.add_message(msg.copy())
