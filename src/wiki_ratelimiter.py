import logging
from urllib.parse import urlparse

logger = logging.getLogger("rcgcdw.ratelimiter")

class RateLimiter:
	def __init__(self):
		self.domain_requests: dict = {}

	def get_timeout(self, url):
