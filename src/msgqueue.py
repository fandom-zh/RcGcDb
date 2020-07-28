import asyncio, logging, aiohttp
from src.discord import send_to_discord_webhook
from src.config import settings
from collections import defaultdict, ItemsView
logger = logging.getLogger("rcgcdw.msgqueue")

class MessageQueue:
	"""Message queue class for undelivered messages"""
	def __init__(self):
		self._queue = []
		self.session = None

	def __repr__(self):
		return self._queue

	def __len__(self):
		return len(self._queue)

	def __iter__(self):
		return iter(self._queue)

	def clear(self):
		self._queue.clear()

	def add_message(self, message):
		self._queue.append(message)

	def cut_messages(self, item_num):
		self._queue = self._queue[item_num:]

	async def create_session(self):
		self.session = aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(5.0))

	async def group_by_webhook(self):  # TODO Change into iterable
		"""Group Discord messages in the queue by the dictionary, allowing to send multiple messages to different
		webhooks at the same time avoiding ratelimits per Discord webhook route."""
		message_dict = defaultdict(list)
		for msg in self._queue:
			for webhook in msg.webhook_url:
				message_dict[webhook].append(msg)
		return message_dict.items()

	async def send_msg_set(self, msg_set: tuple):
		webhook_url, messages = msg_set
		for msg in messages:
			if await send_to_discord_webhook(msg, webhook_url) < 2:
				logger.debug("Sending message succeeded")
				self._queue.remove(msg)
				await asyncio.sleep(1.9)
			else:
				logger.debug("Sending message failed")
				break

	async def resend_msgs(self):
		if self._queue:
			logger.info(
				"{} messages waiting to be delivered to Discord.".format(len(self._queue)))
			tasks_to_run = []
			for set_msgs in await self.group_by_webhook():
				logger.debug(set_msgs)
				tasks_to_run.append(self.send_msg_set(set_msgs))
			await asyncio.gather(*tasks_to_run)
			logger.debug(self._queue)
		await asyncio.sleep(0.1)


messagequeue = MessageQueue()


async def send_to_discord(msg):
	messagequeue.add_message(msg)
