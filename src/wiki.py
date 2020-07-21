from dataclasses import dataclass
import re
import logging, aiohttp
from src.exceptions import *
from src.database import db_cursor, db_connection
from src.formatters.rc import embed_formatter, compact_formatter
from src.misc import LinkParser
from src.i18n import langs
import src.discord
from src.config import settings
from bs4 import BeautifulSoup

logger = logging.getLogger("rcgcdb.wiki")

supported_logs = ["protect/protect", "protect/modify", "protect/unprotect", "upload/overwrite", "upload/upload", "delete/delete", "delete/delete_redir", "delete/restore", "delete/revision", "delete/event", "import/upload", "import/interwiki", "merge/merge", "move/move", "move/move_redir", "protect/move_prot", "block/block", "block/unblock", "block/reblock", "rights/rights", "rights/autopromote", "abusefilter/modify", "abusefilter/create", "interwiki/iw_add", "interwiki/iw_edit", "interwiki/iw_delete", "curseprofile/comment-created", "curseprofile/comment-edited", "curseprofile/comment-deleted", "curseprofile/comment-purged", "curseprofile/profile-edited", "curseprofile/comment-replied", "contentmodel/change", "sprite/sprite", "sprite/sheet", "sprite/slice", "managetags/create", "managetags/delete", "managetags/activate", "managetags/deactivate", "tag/update", "cargo/createtable", "cargo/deletetable", "cargo/recreatetable", "cargo/replacetable", "upload/revert"]


@dataclass
class Wiki:
	mw_messages: int = None
	fail_times: int = 0  # corresponding to amount of times connection with wiki failed for client reasons (400-499)
	session: aiohttp.ClientSession = None

	async def create_session(self):
		self.session = aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(5.0))

	async def fetch_wiki(self, extended, script_path) -> aiohttp.ClientResponse:
		if self.session is None:
			await self.create_session()
		url_path = script_path + "api.php"
		amount = 20
		if extended:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "meta": "allmessages|siteinfo",
			          "utf8": 1, "tglimit": "max", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rctype": "edit|new|log|external",
			          "ammessages": "recentchanges-page-added-to-category|recentchanges-page-removed-from-category|recentchanges-page-added-to-category-bundled|recentchanges-page-removed-from-category-bundled",
			          "amenableparser": 1, "amincludelocal": 1, "siprop": "namespaces|general"}
		else:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "meta": "siteinfo", "utf8": 1,
			          "tglimit": "max", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rctype": "edit|new|log|external", "siprop": "namespaces|general"}
		try:
			response = await self.session.get(url_path, params=params)
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError):
			logger.exception("A connection error occurred while requesting {}".format(url_path))
			raise WikiServerError
		return response

	async def safe_request(self, url):
		try:
			request = await self.session.get(url, timeout=5, allow_redirects=False)
			request.raise_for_status()
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError):
			logger.exception("Reached connection error for request on link {url}".format(url=url))
			return None
		else:
			return request

	async def check_status(self, wiki_url, status):
		if 199 < status < 300:
			self.fail_times = 0
			pass
		elif 400 < status < 500:  # ignore 400 error since this might be our fault
			self.fail_times += 1
			logger.warning("Wiki {} responded with HTTP code {}, increased fail_times to {}, skipping...".format(wiki_url, status, self.fail_times))
			if self.fail_times > 3:
				await self.remove(wiki_url, status)
			raise WikiError
		elif 499 < status < 600:
			logger.warning("Wiki {} responded with HTTP code {}, skipping...".format(wiki_url, status, self.fail_times))
			raise WikiServerError

	async def remove(self, wiki_id, reason):
		src.discord.wiki_removal(wiki_id, reason)
		src.discord.wiki_removal_monitor(wiki_id, reason)
		db_cursor.execute("DELETE FROM rcgcdw WHERE wiki = ?", wiki_id)
		logger.warning("{} rows affected by DELETE FROM rcgcdw WHERE wiki = {}".format(db_cursor.rowcount, wiki_id))
		db_connection.commit()

	async def pull_comment(self, comment_id, WIKI_API_PATH):
		try:
			comment = await self.safe_request(
				"{wiki}?action=comment&do=getRaw&comment_id={comment}&format=json".format(wiki=WIKI_API_PATH,
				                                                                          comment=comment_id)).json()[
				"text"]
			logger.debug("Got the following comment from the API: {}".format(comment))
		except (TypeError, AttributeError):
			logger.exception("Could not resolve the comment text.")
		except KeyError:
			logger.exception("CurseProfile extension API did not respond with a valid comment content.")
		else:
			if len(comment) > 1000:
				comment = comment[0:1000] + "…"
			return comment
		return ""


async def process_cats(event: dict, local_wiki: Wiki, category_msgs: dict, categorize_events: dict):
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
	# if same entry is not in mw_msgs
	key = len(mw_msgs)
	mw_msgs[key] = msgs  # it may be a little bit messy for sure, however I don't expect any reason to remove mw_msgs entries by one
	local_wiki.mw_messages = key

async def essential_info(change: dict, changed_categories, local_wiki: Wiki, db_wiki: tuple, target: tuple, paths: tuple, request: dict):
	"""Prepares essential information for both embed and compact message format."""
	def _(string: str) -> str:
		"""Our own translation string to make it compatible with async"""
		return lang.gettext(string)

	lang = langs[target[0][0]]
	ngettext = lang.ngettext
	# recent_changes = RecentChangesClass()  # TODO Look into replacing RecentChangesClass with local_wiki
	LinkParser = LinkParser("domain")
	logger.debug(change)
	appearance_mode = embed_formatter if target[0][1] > 0 else compact_formatter
	if ("actionhidden" in change or "suppressed" in change):  # if event is hidden using suppression
		await appearance_mode("suppressed", change, "", changed_categories, local_wiki, target, _, ngettext, paths)
		return
	if "commenthidden" not in change:
		LinkParser.feed(change["parsedcomment"])
		parsed_comment = LinkParser.new_string
		LinkParser.new_string = ""
		parsed_comment = re.sub(r"(`|_|\*|~|{|}|\|\|)", "\\\\\\1", parsed_comment, 0)
	else:
		parsed_comment = _("~~hidden~~")
	if not parsed_comment:
		parsed_comment = None
	if change["type"] in ["edit", "new"]:
		logger.debug("List of categories in essential_info: {}".format(changed_categories))
		if "userhidden" in change:
			change["user"] = _("hidden")
		identification_string = change["type"]
	elif change["type"] == "log":
		identification_string = "{logtype}/{logaction}".format(logtype=change["logtype"], logaction=change["logaction"])
		if identification_string not in supported_logs:
			logger.warning(
				"This event is not implemented in the script. Please make an issue on the tracker attaching the following info: wiki url, time, and this information: {}".format(
					change))
			return
	elif change["type"] == "categorize":
		return
	else:
		logger.warning("This event is not implemented in the script. Please make an issue on the tracker attaching the following info: wiki url, time, and this information: {}".format(change))
		return
	additional_data = {"namespaces": request["query"]["namespaces"], "tags": {}}
	for tag in request["query"]["tags"]:
		try:
			additional_data["tags"][tag["name"]] = (BeautifulSoup(tag["displayname"], "lxml")).get_text()
		except KeyError:
			additional_data["tags"][tag["name"]] = None  # Tags with no displ
	await appearance_mode(identification_string, change, parsed_comment, changed_categories, local_wiki, target, _, ngettext, paths, additional_data=additional_data)
