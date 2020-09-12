import asyncio, logging, aiohttp
from src.discord import send_to_discord_webhook
from src.config import settings
from collections import defaultdict
logger = logging.getLogger("rcgcdw.msgqueue")

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

	def add_message(self, message):
		self._queue.append(message)

	def cut_messages(self, item_num):
		self._queue = self._queue[item_num:]


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
			if self.global_rate_limit:
				return  # if we are globally rate limited just wait for first gblocked request to finish
			status = await send_to_discord_webhook(msg, webhook_url)
			if status[0] < 2:
				logger.debug("Sending message succeeded")
				try:
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
			await asyncio.gather(*tasks_to_run)
			# logger.debug(self._queue)
		else:
			await asyncio.sleep(0.5)


messagequeue = MessageQueue()


async def send_to_discord(msg):
	messagequeue.add_message(msg)
