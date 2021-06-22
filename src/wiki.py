from dataclasses import dataclass
import re
import logging, aiohttp

from mw_messages import MWMessages
from src.exceptions import *
from src.database import db
from src.formatters.rc import embed_formatter, compact_formatter
from src.formatters.discussions import feeds_embed_formatter, feeds_compact_formatter
from src.misc import parse_link
from src.i18n import langs
from src.wiki_ratelimiter import RateLimiter
from statistics import Statistics
import sqlite3
import src.discord
import asyncio
from src.config import settings
# noinspection PyPackageRequirements
from bs4 import BeautifulSoup
from collections import OrderedDict
from typing import Union, Optional

logger = logging.getLogger("rcgcdb.wiki")


class Wiki:
	def __init__(self, script_url: str, rc_id: int, discussion_id: int):
		self.script_url: str = script_url
		self.session = aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(6.0))
		self.statistics: Statistics = Statistics(rc_id, discussion_id)
		self.fail_times: int = 0
		self.mw_messages: Optional[MWMessages] = None  # TODO Need to initialize MWMessages() somewhere
		self.first_fetch_done: bool = False

	@property
	def rc_id(self):
		return self.statistics.last_action

	@staticmethod
	async def remove(wiki_url, reason):
		logger.info("Removing a wiki {}".format(wiki_url))
		await src.discord.wiki_removal(wiki_url, reason)
		await src.discord.wiki_removal_monitor(wiki_url, reason)
		async with db.pool().acquire() as connection:
			result = await connection.execute('DELETE FROM rcgcdw WHERE wiki = $1', wiki_url)
		logger.warning('{} rows affected by DELETE FROM rcgcdw WHERE wiki = "{}"'.format(result, wiki_url))

	def downtime_controller(self, down):  # TODO Finish this one
		if down:
			self.fail_times += 1

		else:
			self.fail_times -= 1

	def parse_mw_request_info(self, request_data: dict, url: str):
		"""A function parsing request JSON message from MediaWiki logging all warnings and raising on MediaWiki errors"""
		# any([True for k in request_data.keys() if k in ("error", "errors")])
		errors: list = request_data.get("errors", {})  # Is it ugly? I don't know tbh
		if errors:
			raise MediaWikiError(str(errors))
		warnings: list = request_data.get("warnings", {})
		if warnings:
			for warning in warnings:
				logger.warning("MediaWiki returned the following warning: {code} - {text} on {url}.".format(
					code=warning["code"], text=warning.get("text", warning.get("*", "")), url=url
				))
		return request_data

	async def api_request(self, params: Union[str, OrderedDict], *json_path: str, timeout: int = 10,
					allow_redirects: bool = False) -> dict:
		"""Method to GET request data from the wiki's API with error handling including recognition of MediaWiki errors.

		Parameters:

			params (str, OrderedDict): a string or collections.OrderedDict object containing query parameters
			json_path (str): *args taking strings as values. After request is parsed as json it will extract data from given json path
			timeout (int, float) (default=10): int or float limiting time required for receiving a full response from a server before returning TimeoutError
			allow_redirects (bool) (default=False): switches whether the request should follow redirects or not

		Returns:

			request_content (dict): a dict resulting from json extraction of HTTP GET request with given json_path
			OR
			One of the following exceptions:
			ServerError: When connection with the wiki failed due to server error
			ClientError: When connection with the wiki failed due to client error
			KeyError: When json_path contained keys that weren't found in response JSON response
			BadRequest: When params argument is of wrong type
			MediaWikiError: When MediaWiki returns an error
		"""
		# Making request
		try:
			if isinstance(params,
						  str):  # Todo Make it so there are some default arguments like warning/error format appended
				request = await self.session.get(self.script_url + "api.php?" + params + "&errorformat=raw", timeout=timeout,
										   allow_redirects=allow_redirects)
			elif isinstance(params, OrderedDict):
				params["errorformat"] = "raw"
				request = await self.session.get(self.script_url + "api.php", params=params, timeout=timeout,
										   allow_redirects=allow_redirects)
			else:
				raise BadRequest(params)
		except (aiohttp.ServerConnectionError, aiohttp.ServerTimeoutError) as exc:
			logger.warning("Reached {error} error for request on link {url}".format(error=repr(exc),
																					url=self.script_url + str(params)))
			self.downtime_controller(True)
			raise ServerError
		# Catching HTTP errors
		if 499 < request.status < 600:
			self.downtime_controller(True)
			raise ServerError
		elif request.status == 302:
			logger.critical(
				"Redirect detected! Either the wiki given in the script settings (wiki field) is incorrect/the wiki got removed or is giving us the false value. Please provide the real URL to the wiki, current URL redirects to {}".format(
					request.url))
		elif 399 < request.status < 500:
			logger.error("Request returned ClientError status code on {url}".format(url=request.url))
			raise ClientError(request)
		else:
			# JSON Extraction
			try:
				request_json = self.parse_mw_request_info(await request.json(encoding="UTF-8"), str(request.url))
				for item in json_path:
					request_json = request_json[item]
			except ValueError:
				logger.warning("ValueError when extracting JSON data on {url}".format(url=request.url))
				self.downtime_controller(True)
				raise ServerError
			except MediaWikiError:
				logger.exception("MediaWiki error on request: {}".format(request.url))
				raise
			except KeyError:
				logger.exception("KeyError while iterating over json_path, full response: {}".format(request.json()))
				raise
		self.first_fetch_done = True
		return request_json

	async def fetch_wiki(self, amount=20) -> dict:
		if self.first_fetch_done is False:
			params = OrderedDict({"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
					  "meta": "allmessages|siteinfo",
					  "utf8": 1, "tglimit": "max", "tgprop": "displayname",
					  "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
					  "rclimit": amount, "rcshow": "!bot", "rctype": "edit|new|log|categorize",
					  "ammessages": "recentchanges-page-added-to-category|recentchanges-page-removed-from-category|recentchanges-page-added-to-category-bundled|recentchanges-page-removed-from-category-bundled",
					  "amenableparser": 1, "amincludelocal": 1, "siprop": "namespaces|general"})
		else:
			params = OrderedDict({"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
					  "meta": "siteinfo", "utf8": 1,
					  "tglimit": "max", "rcshow": "!bot", "tgprop": "displayname",
					  "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
					  "rclimit": amount, "rctype": "edit|new|log|categorize", "siprop": "namespaces|general"})
		try:
			response = await self.api_request(params=params)
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError):
			logger.error("A connection error occurred while requesting {}".format(params))
			raise WikiServerError
		return response

	def scan(self):
		try:
			request = await self.fetch_wiki()
		except WikiServerError:
			self.downtime_controller(True)
			return  # TODO Add a log entry?
		else:
			self.downtime_controller(False)
		if not self.mw_messages:
			mw_messages = request.get("query")

@dataclass
class Wiki_old:
	mw_messages: int = None
	fail_times: int = 0  # corresponding to amount of times connection with wiki failed for client reasons (400-499)
	session: aiohttp.ClientSession = None
	rc_active: int = 0
	last_check: float = 0.0
	last_discussion_check: float = 0.0

	@staticmethod
	async def fetch_wiki(extended, script_path, session: aiohttp.ClientSession, ratelimiter: RateLimiter, amount=20) -> aiohttp.ClientResponse:
		await ratelimiter.timeout_wait()
		url_path = script_path + "api.php"
		if extended:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "meta": "allmessages|siteinfo",
			          "utf8": 1, "tglimit": "max", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rcshow": "!bot", "rctype": "edit|new|log|categorize",
			          "ammessages": "recentchanges-page-added-to-category|recentchanges-page-removed-from-category|recentchanges-page-added-to-category-bundled|recentchanges-page-removed-from-category-bundled",
			          "amenableparser": 1, "amincludelocal": 1, "siprop": "namespaces|general"}
		else:
			params = {"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
			          "meta": "siteinfo", "utf8": 1,
			          "tglimit": "max", "rcshow": "!bot", "tgprop": "displayname",
			          "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user",
			          "rclimit": amount, "rctype": "edit|new|log|categorize", "siprop": "namespaces|general"}
		try:
			response = await session.get(url_path, params=params)
			ratelimiter.timeout_add(1.0)
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError):
			logger.error("A connection error occurred while requesting {}".format(url_path))
			raise WikiServerError
		return response

	@staticmethod
	async def fetch_feeds(wiki, session: aiohttp.ClientSession) -> aiohttp.ClientResponse:
		url_path = "{wiki}wikia.php".format(wiki=wiki)
		params = {"controller": "DiscussionPost", "method": "getPosts", "includeCounters": "false", "sortDirection": "descending", "sortKey": "creation_date", "limit": 20}
		try:
			response = await session.get(url_path, params=params)
			response.raise_for_status()
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError, aiohttp.ClientResponseError):
			logger.error("A connection error occurred while requesting {}".format(url_path))
			raise WikiServerError
		return response

	@staticmethod
	async def safe_request(url, ratelimiter, *keys):
		await ratelimiter.timeout_wait()
		try:
			async with aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(6.0)) as session:
				request = await session.get(url)
				ratelimiter.timeout_add(1.0)
				request.raise_for_status()
				json_request = await request.json(encoding="UTF-8")
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError):
			logger.error("Reached connection error for request on link {url}".format(url=url))
		else:
			try:
				for item in keys:
					json_request = json_request[item]
			except KeyError:
				logger.warning(
					"Failure while extracting data from request on key {key} in {change}".format(key=item, change=json_request))
				return None
			return json_request

	async def fail_add(self, wiki_url, status):
		logger.debug("Increasing fail_times to {}".format(self.fail_times+3))
		self.fail_times += 3
		if self.fail_times > 9:
			await self.remove(wiki_url, status)

	async def check_status(self, wiki_url, status):
		if 199 < status < 300:
			self.fail_times -= 1
			pass
		elif 400 < status < 500:  # ignore 400 error since this might be our fault
			await self.fail_add(wiki_url, status)
			logger.warning("Wiki {} responded with HTTP code {}, increased fail_times to {}, skipping...".format(wiki_url, status, self.fail_times))
			raise WikiError
		elif 499 < status < 600:
			logger.warning("Wiki {} responded with HTTP code {}, skipping...".format(wiki_url, status, self.fail_times))
			raise WikiServerError

	@staticmethod
	async def remove(wiki_url, reason):
		logger.info("Removing a wiki {}".format(wiki_url))
		await src.discord.wiki_removal(wiki_url, reason)
		await src.discord.wiki_removal_monitor(wiki_url, reason)
		async with db.pool().acquire() as connection:
			result = await connection.execute('DELETE FROM rcgcdw WHERE wiki = $1', wiki_url)
		logger.warning('{} rows affected by DELETE FROM rcgcdw WHERE wiki = "{}"'.format(result, wiki_url))

	async def pull_comment(self, comment_id, WIKI_API_PATH, rate_limiter):
		try:
			comment = await self.safe_request(
				"{wiki}?action=comment&do=getRaw&comment_id={comment}&format=json".format(wiki=WIKI_API_PATH,
				                                                                          comment=comment_id), rate_limiter, "text")
			logger.debug("Got the following comment from the API: {}".format(comment))
			if comment is None:
				raise TypeError
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
	"""Process categories based on local MW messages. """
	if event["type"] == "categorize":
		if "commenthidden" not in event:
			if local_wiki.mw_messages is not None:
				cat_title = event["title"].split(':', 1)[1]
				# I so much hate this, blame Markus for making me do this
				if event["revid"] not in categorize_events:
					categorize_events[event["revid"]] = {"new": set(), "removed": set()}
				comment_to_match = re.sub(r'<.*?a>', '', event["parsedcomment"])
				wiki_cat_mw_messages = category_msgs[local_wiki.mw_messages]
				if wiki_cat_mw_messages[0][1] in comment_to_match or wiki_cat_mw_messages[2][1] in comment_to_match:  # Added to category
					categorize_events[event["revid"]]["new"].add(cat_title)
					#logger.debug("Matched {} to added category for {}".format(cat_title, event["revid"]))
				elif wiki_cat_mw_messages[1][1] in comment_to_match or wiki_cat_mw_messages[3][1] in comment_to_match:  # Removed from category
					categorize_events[event["revid"]]["removed"].add(cat_title)
					#logger.debug("Matched {} to removed category for {}".format(cat_title, event["revid"]))
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
	for message in wiki_response["query"]["allmessages"]:
		if not "missing" in message:  # ignore missing strings
			msgs.append((message["name"], re.sub(r'\[\[.*?\]\]', '', message["*"])))
		else:
			logger.warning("Could not fetch the MW message translation for: {}".format(message["name"]))
	msgs = tuple(msgs)
	for key, set in mw_msgs.items():
		if msgs == set:
			local_wiki.mw_messages = key
			return
	# if same entry is not in mw_msgs
	key = len(mw_msgs)
	mw_msgs[key] = msgs  # it may be a little bit messy for sure, however I don't expect any reason to remove mw_msgs entries by one
	local_wiki.mw_messages = key


# db_wiki: webhook, wiki, lang, display, rcid, postid
async def essential_info(change: dict, changed_categories, local_wiki: Wiki, target: tuple, paths: tuple, request: dict,
                         rate_limiter: RateLimiter) -> src.discord.DiscordMessage:
	"""Prepares essential information for both embed and compact message format."""
	_ = langs[target[0][0]]["wiki"].gettext
	changed_categories = changed_categories.get(change["revid"], None)
	#logger.debug("List of categories in essential_info: {}".format(changed_categories))
	appearance_mode = embed_formatter if target[0][1] > 0 else compact_formatter
	if "actionhidden" in change or "suppressed" in change:  # if event is hidden using suppression
		await appearance_mode("suppressed", change, "", changed_categories, local_wiki, target, paths, rate_limiter)
		return
	if "commenthidden" not in change:
		parsed_comment = parse_link(paths[3], change["parsedcomment"])
	else:
		parsed_comment = _("~~hidden~~")
	if not parsed_comment:
		parsed_comment = None
	if change["type"] in ["edit", "new"]:
		if "userhidden" in change:
			change["user"] = _("hidden")
		identification_string = change["type"]
	elif change["type"] == "log":
		identification_string = "{logtype}/{logaction}".format(logtype=change["logtype"], logaction=change["logaction"])
	elif change["type"] == "categorize":
		return
	else:
		identification_string = change["type"]
	additional_data = {"namespaces": request["query"]["namespaces"], "tags": {}}
	for tag in request["query"]["tags"]:
		try:
			additional_data["tags"][tag["name"]] = (BeautifulSoup(tag["displayname"], "lxml")).get_text()
		except KeyError:
			additional_data["tags"][tag["name"]] = None  # Tags with no displ
	return await appearance_mode(identification_string, change, parsed_comment, changed_categories, local_wiki, target, paths, rate_limiter, additional_data=additional_data)


async def essential_feeds(change: dict, comment_pages: dict, db_wiki: sqlite3.Row, target: tuple) -> src.discord.DiscordMessage:
	"""Prepares essential information for both embed and compact message format."""
	appearance_mode = feeds_embed_formatter if target[0][1] > 0 else feeds_compact_formatter
	identification_string = change["_embedded"]["thread"][0]["containerType"]
	comment_page = None
	if identification_string == "ARTICLE_COMMENT" and comment_pages is not None:
		comment_page = comment_pages.get(change["forumId"], None)
		if comment_page is not None:
			comment_page["fullUrl"] = "/".join(db_wiki["wiki"].split("/", 3)[:3]) + comment_page["relativeUrl"]
	return await appearance_mode(identification_string, change, target, db_wiki["wiki"], article_page=comment_page)
