import logging, time, asyncio

logger = logging.getLogger("rcgcdw.ratelimiter")

class RateLimiter:
	def __init__(self):
		self.timeout_until = 0

	def timeout_add(self, timeout: float):
		"""This function sets a new timeout"""
		self.timeout_until = time.time() + timeout
		#logger.debug("Added {} timeout".format(timeout))

	async def timeout_wait(self):
		"""This awaitable calculates the time to wait according to timeout_until, does not wait if it's past the timeout to not skip a cycle"""
		calculated_timeout = self.timeout_until - time.time()
		#logger.debug("Waiting {}".format(calculated_timeout))
		if calculated_timeout > 0:
			await asyncio.sleep(calculated_timeout)
