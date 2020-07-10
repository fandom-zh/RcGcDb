from dataclasses import dataclass
from src.session import session
import logging, aiohttp
from src.exceptions import *
from src.database import db_cursor
import src.discord

logger = logging.getLogger("rcgcdb.wiki")

@dataclass
class Wiki:
	mw_messages: int = None
	fail_times: int = 0  # corresponding to amount of times connection with wiki failed for client reasons (400-499)

	async def fetch_wiki(self, extended, script_path, api_path) -> aiohttp.ClientResponse:
		url_path = script_path + api_path
		amount = 20
		if extended:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "meta": "allmessages|siteinfo",
			          "utf8": 1, "tglimit": "max", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rctype": "edit|new|log|external",
			          "ammessages": "recentchanges-page-added-to-category|recentchanges-page-removed-from-category|recentchanges-page-added-to-category-bundled|recentchanges-page-removed-from-category-bundled",
			          "amenableparser": 1, "amincludelocal": 1, "siprop": "namespaces"}
		else:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "utf8": 1,
			          "tglimit": "max", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rctype": "edit|new|log|external", "siprop": "namespaces"}
		try:
			response = await session.get(url_path, params=params)
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError):
			logger.exception("A connection error occurred while requesting {}".format(url_path))
			raise WikiServerError
		return response

	async def check_status(self, wiki_id, status, name):
		if 199 < status < 300:
			self.fail_times = 0
			pass
		elif 400 < status < 500:  # ignore 400 error since this might be our fault
			self.fail_times += 1
			logger.warning("Wiki {} responded with HTTP code {}, increased fail_times to {}, skipping...".format(name, status, self.fail_times))
			if self.fail_times > 3:
				await self.remove(wiki_id, status)
			raise WikiError
		elif 499 < status < 600:
			logger.warning("Wiki {} responded with HTTP code {}, skipping...".format(name, status, self.fail_times))
			raise WikiServerError

	async def remove(self, wiki_id, reason):
		src.discord.wiki_removal()