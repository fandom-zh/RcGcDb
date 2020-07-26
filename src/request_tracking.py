import aiohttp
import logging
from src.config import settings

logger = logging.getLogger("rcgcdb.request_tracking")

class WikiRequestTracking:
	def __init__(self):
		self.current_timeout = 0

	async def add_timeout(self, time: float):
		self.current_timeout += time

	def is_fandom(self, url):
		if any(x in url for x in ("fandom.com", "gamepedia.com", "wikia.org")):
			return True
		return False

async def on_request_start(session, trace_config_ctx, params):
	if

trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)