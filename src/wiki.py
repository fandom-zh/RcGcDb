from dataclasses import dataclass
from src.session import session
import re
import logging, aiohttp
from src.exceptions import *
from src.database import db_cursor, db_connection
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
		src.discord.wiki_removal(wiki_id, reason)
		src.discord.wiki_removal_monitor(wiki_id, reason)
		db_cursor.execute("DELETE FROM observers WHERE wiki_id = ?", wiki_id)
		db_cursor.execute("DELETE FROM wikis WHERE ROWID = ?", wiki_id)
		db_connection.commit()


async def process_event(event: dict, local_wiki: Wiki, category_msgs: dict):
	categorize_events = {}
	if event["type"] == "categorize":
		if "commenthidden" not in event:
			if local_wiki.mw_messages:
				cat_title = event["title"].split(':', 1)[1]
				# I so much hate this, blame Markus for making me do this
				if event["revid"] not in categorize_events:
					categorize_events[event["revid"]] = {"new": set(), "removed": set()}
				comment_to_match = re.sub(r'<.*?a>', '', event["parsedcomment"])
				wiki_cat_mw_messages = category_msgs[local_wiki.mw_messages]
				if wiki_cat_mw_messages[0] in comment_to_match or wiki_cat_mw_messages[2] in comment_to_match:  # Added to category
					categorize_events[event["revid"]]["new"].add(cat_title)
					logger.debug("Matched {} to added category for {}".format(cat_title, event["revid"]))
				elif wiki_cat_mw_messages[1] in comment_to_match or wiki_cat_mw_messages[3] in comment_to_match:  # Removed from category
					categorize_events[event["revid"]]["removed"].add(cat_title)
					logger.debug("Matched {} to removed category for {}".format(cat_title, event["revid"]))
				else:
					logger.debug(
						"Unknown match for category change with messages {}, {}, {}, {} and comment_to_match {}".format(
							wiki_cat_mw_messages[0], wiki_cat_mw_messages[1], wiki_cat_mw_messages[2], wiki_cat_mw_messages[3],
							comment_to_match))
			else:
				logger.warning(
					"Init information not available, could not read category information. Please restart the bot.")
		else:
			logger.debug("Log entry got suppressed, ignoring entry.")


async def process_mwmsgs(wiki_response: dict, local_wiki: Wiki, mw_msgs: dict):
	"""
	This function is made to parse the initial wiki extended information to update local_wiki.mw_messages that stores the key
	to mw_msgs that is a dict storing id: tuple where tuple is a set of MW messages for categories.
	The reason it's constructed this way is to prevent duplication of data in memory so Markus doesn't complain about
	high RAM usage. It does however affect CPU performance as every wiki requires to check the list for the matching
	tuples of MW messages.

	:param wiki_response:
	:param local_wiki:
	:param mw_msgs:
	:return:
	"""
	msgs = []
	for message in wiki_response["allmessages"]:
		if not "missing" in message:  # ignore missing strings
			msgs.append((message["name"], re.sub(r'\[\[.*?\]\]', '', message["*"])))
		else:
			logging.warning("Could not fetch the MW message translation for: {}".format(message["name"]))
	msgs = tuple(msgs)
	for key, set in mw_msgs.items():
		if msgs == set:
			local_wiki.mw_messages = key
			return
	key = len(mw_msgs)
	mw_msgs[key] = msgs  # it may be a little bit messy for sure, however I don't expect any reason to remove mw_msgs entries by one
	local_wiki.mw_messages = key
