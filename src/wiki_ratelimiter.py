import logging

logger = logging.getLogger("rcgcdw.ratelimiter")

class RateLimiter:
	def __init__(self):
		self.domain_requests: dict = {}
