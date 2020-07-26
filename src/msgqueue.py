import asyncio, logging, aiohttp
from src.discord import send_to_discord_webhook
from src.config import settings
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

	async def resend_msgs(self):
		if self.session is None:
			await self.create_session()
		if self._queue:
			logger.info(
				"{} messages waiting to be delivered to Discord.".format(len(self._queue)))
			for num, item in enumerate(self._queue):
				logger.debug(
					"Trying to send a message to Discord from the queue with id of {} and content {}".format(str(num),
					                                                                                         str(item)))
				if await send_to_discord_webhook(item) < 2:
					logger.debug("Sending message succeeded")
					await asyncio.sleep(1.9)
				else:
					logger.debug("Sending message failed")
					break
			else:
				self.clear()
				logger.debug("Queue emptied, all messages delivered")
			self.cut_messages(num)
			logger.debug(self._queue)
		await asyncio.sleep(4.0)


messagequeue = MessageQueue()


async def send_to_discord(msg):
	messagequeue.add_message(msg)
