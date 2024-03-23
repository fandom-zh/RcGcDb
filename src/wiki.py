from __future__ import annotations

import functools
import time
import re
import logging, aiohttp
import asyncio
import requests

from src.api.util import default_message
from src.misc import prepare_settings, run_hooks
from src.discord.queue import messagequeue, QueueEntry
from src.mw_messages import MWMessages
from src.exceptions import *
from src.queue_handler import dbmanager
from src.api.hooks import formatter_hooks, pre_hooks, post_hooks
from src.api.client import Client
from src.api.context import Context
from src.discord.message import DiscordMessage, DiscordMessageMetadata, StackedDiscordMessage
from src.i18n import langs
from src.statistics import Statistics, Log, LogType
from src.config import settings
# noinspection PyPackageRequirements
from bs4 import BeautifulSoup
from collections import OrderedDict, defaultdict, namedtuple
from typing import Union, Optional, TYPE_CHECKING, List

Settings = namedtuple("Settings", ["lang", "display", "buttons"])
logger = logging.getLogger("rcgcdb.wiki")

# wiki_reamoval_reasons = {410: _("wiki deleted"), 404: _("wiki deleted"), 401: _("wiki inaccessible"),
# 				           402: _("wiki inaccessible"), 403: _("wiki inaccessible"), 1000: _("discussions disabled")}

if TYPE_CHECKING:
	from src.domain import Domain

MESSAGE_LIMIT = settings.get("message_limit", 30)


class Wiki:
	def __init__(self, script_url: str, rc_id: Optional[int], discussion_id: Optional[str]):
		self.script_url: str = script_url
		self.session: aiohttp.ClientSession = aiohttp.ClientSession(headers=settings["header"], timeout=aiohttp.ClientTimeout(total=6))
		self.statistics: Statistics = Statistics(rc_id, discussion_id)
		self.mw_messages: Optional[MWMessages] = None
		self.tags: dict[str, Optional[str]] = {}  # Tag can be None if hidden
		self.first_fetch_done: bool = False
		self.domain: Optional[Domain] = None
		self.rc_targets: Optional[defaultdict[Settings, list[str]]] = None
		self.discussion_targets: Optional[defaultdict[Settings, list[str]]] = None
		self.client: Client = Client(formatter_hooks, self)
		self.message_history: list[StackedDiscordMessage] = list()
		self.namespaces: Optional[dict] = None
		self.recache_requested: bool = False
		self.session_requests = requests.Session()
		self.session_requests.headers.update(settings["header"])
		logger.debug("Creating new wiki object for {}".format(script_url))

	def __str__(self):
		return self.__repr__()

	def __repr__(self):
		return (
			f"<statistics={self.statistics} tags={self.tags} first_fetch_done={self.first_fetch_done}, rc_targets={self.rc_targets}, discussion_targets={self.discussion_targets},"
			f"recache_requested={self.recache_requested}>")

	@property
	def rc_id(self):
		return self.statistics.last_action

	@property
	def discussion_id(self):
		return self.statistics.last_post

	@property
	def last_request(self):
		return self.statistics.last_request

	@last_request.setter
	def last_request(self, value):
		self.statistics.last_request = value

	# async def remove(self, reason):
	# 	logger.info("Removing a wiki {}".format(self.script_url))
	# 	await src.discord.wiki_removal(self.script_url, reason)
	# 	await src.discord.wiki_removal_monitor(self.script_url, reason)
	# 	async with db.pool().acquire() as connection:
	# 		result = await connection.execute('DELETE FROM rcgcdw WHERE wiki = $1', self.script_url)
	# 	logger.warning('{} rows affected by DELETE FROM rcgcdw WHERE wiki = "{}"'.format(result, self.script_url))

	def add_message(self, message: StackedDiscordMessage):
		self.message_history.append(message)
		if len(self.message_history) > MESSAGE_LIMIT*len(self.rc_targets):
			self.message_history = self.message_history[len(self.message_history)-MESSAGE_LIMIT*len(self.rc_targets):]

	def set_domain(self, domain: Domain):
		self.domain = domain

	def find_middle_next(self, ids: List[str], pageid: int) -> list:
		"""To address #235 RcGcDw should now remove diffs in next revs relative to redacted revs to protect information in revs that revert revdeleted information.
		What this function does, is it fetches all messages for given page and finds revids of the messages that come next after ids
		:arg ids - list
		:arg pageid - int

		:return list"""
		def extract_revid(item: tuple[StackedDiscordMessage, list[int]]):
			rev_ids = set()
			for message_id in sorted(item[1], reverse=True):
				rev_ids.add(item[0].message_list[message_id].metadata.rev_id)
			return rev_ids
		ids = [int(x) for x in ids]
		result = set()
		ids.sort()  # Just to be sure, sort the list to make sure it's always sorted
		search = self.search_message_history({"message_display": 3, "page_id": pageid})
		# messages = db_cursor.execute("SELECT revid FROM event WHERE pageid = ? AND revid >= ? ORDER BY revid",
		# 							 (pageid, ids[0],))
		all_in_page = sorted(set([x for row in map(extract_revid, search) for x in row]))  # Flatten the result
		for ID in ids:
			try:
				result.add(all_in_page[all_in_page.index(ID) + 1])
			except (KeyError, ValueError):
				logger.debug(f"Value {ID} not in {all_in_page} or no value after that.")
		return list(result - set(ids))

	def search_message_history(self, params: dict) -> list[tuple[StackedDiscordMessage, list[int]]]:
		"""Search self.message_history for messages which match all properties in params and return them in a list
		:param params is a dictionary of which messages are compared against. All name and values must be equal for match to return true
		Matches metadata from discord.message.DiscordMessageMetadata
		:returns [(StackedDiscordMessage, [index ids of matching messages in that StackedMessage])]"""
		output = []
		for message in self.message_history:
			returned_matches_for_stacked = message.filter(params)
			if returned_matches_for_stacked:
				output.append((message, [x[0] for x in returned_matches_for_stacked]))
		return output

	def delete_messages(self, params: dict):
		"""Delete certain messages from message_history which DiscordMessageMetadata matches all properties in params"""
		# Delete all messages with given IDs
		for stacked_message, ids in self.search_message_history(params):
			stacked_message.delete_message_by_id(ids)
			# If all messages were removed, send a DELETE to Discord
			if len(stacked_message.message_list) == 0:
				messagequeue.add_message(QueueEntry(stacked_message, [stacked_message.webhook], self, method="DELETE"))
			else:
				messagequeue.add_message(QueueEntry(stacked_message, [stacked_message.webhook], self, method="PATCH"))

	def redact_messages(self, context: Context, ids: list[int], mode: str, censored_properties: dict):
		# ids can refer to multiple events, and search does not support additive mode, so we have to loop it for all ids
		for revlogid in ids:
			for stacked_message, ids in self.search_message_history({mode: revlogid}):  # This might not work depending on how Python handles it, but hey, learning experience
				for message in [message for num, message in enumerate(stacked_message.message_list) if num in ids]:
					if "user" in censored_properties and "url" in message["author"]:
						message["author"]["name"] = context._("hidden")
						message["author"].pop("url")
					if "action" in censored_properties and "url" in message:
						message["title"] = context._("~~hidden~~")
						message["embed"].pop("url")
					if "content" in censored_properties and "fields" in message:
						message["embed"].pop("fields")
					if "comment" in censored_properties:
						message["description"] = context._("~~hidden~~")
				messagequeue.add_message(QueueEntry(stacked_message, [stacked_message.webhook], self, method="PATCH"))

	# async def downtime_controller(self, down, reason=None):
	# 	if down:
	# 		self.fail_times += 1
	# 		if self.fail_times > 20:
	# 			await self.remove(reason)
	# 	else:
	# 		self.fail_times -= 1

	async def update_targets(self) -> None:
		"""This function generates all possible varations of outputs that we need to generate messages for.

		:returns defaultdict[namedtuple, list[str]] - where namedtuple is a named tuple with settings for given webhooks in list"""
		target_settings: defaultdict[Settings, list[str]] = defaultdict(list)
		discussion_targets: defaultdict[Settings, list[str]] = defaultdict(list)
		async for webhook in dbmanager.fetch_rows("SELECT webhook, lang, display, rcid, postid, buttons FROM rcgcdb WHERE wiki = $1", self.script_url):
			if webhook['rcid'] == -1 and webhook['postid'] == '-1':
				await self.remove_wiki_from_db(4)
			if webhook['rcid'] != -1:
				target_settings[Settings(webhook["lang"], webhook["display"], webhook["buttons"])].append(webhook["webhook"])
			if webhook['postid'] != '-1':
				discussion_targets[Settings(webhook["lang"], webhook["display"], webhook["buttons"])].append(webhook["webhook"])
		self.rc_targets = target_settings
		self.discussion_targets = discussion_targets


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
			if isinstance(params, str):
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
			raise ServerError
		# Catching HTTP errors
		if 499 < request.status < 600:
			logger.warning(f"A request to {self.script_url} {params} resulted in {request.status}")
			raise ServerError
		elif request.status == 302:
			logger.critical(
				"Redirect detected! Either the wiki given in the script settings (wiki field) is incorrect/the wiki got removed or is giving us the false value. Please provide the real URL to the wiki, current URL redirects to {}".format(
					request.url))
		elif 399 < request.status < 500:
			logger.error("Request returned ClientError status code on {url}".format(url=request.url))
			self.statistics.update(Log(type=LogType.HTTP_ERROR, title="{} error".format(request.status), details=str(request.headers) + "\n" + str(request.url)))
			raise ClientError(request)
		else:
			# JSON Extraction
			try:
				request_json = self.parse_mw_request_info(await request.json(encoding="UTF-8"), str(request.url))
				for item in json_path:
					request_json = request_json[item]
			except ValueError:
				logger.warning("ValueError when extracting JSON data on {url}".format(url=request.url))
				raise ServerError
			except MediaWikiError:
				logger.exception("MediaWiki error on request: {}".format(request.url))
				raise
			except KeyError:
				logger.exception("KeyError while iterating over json_path, full response: {}".format(request.json()))
				raise
		return request_json

	def sync_api_request(self, params: Union[str, OrderedDict], *json_path: str, timeout: int = 10,
						 allow_redirects: bool = False) -> dict:
		"""Synchronous function based on api_request created for compatibility reasons with RcGcDw API"""
		try:
			if isinstance(params, str):
				request = self.session_requests.get(self.script_url + "api.php" + params + "&errorformat=raw", timeout=10, allow_redirects=allow_redirects)
			elif isinstance(params, OrderedDict):
				request = self.session_requests.get(self.script_url + "api.php", params=params, timeout=10, allow_redirects=allow_redirects)
			else:
				raise BadRequest(params)
		except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
			logger.warning("Reached {error} error for request on link {url}".format(error=repr(exc),
																					url=self.client.WIKI_API_PATH + str(params)))
			raise ServerError
		if 499 < request.status_code < 600:
			logger.warning(f"A request to {self.script_url} {params} resulted in {request.status}")
			raise ServerError
		elif request.status_code == 302:
			logger.critical(
				"Redirect detected! Either the wiki given in the script settings (wiki field) is incorrect/the wiki got removed or is giving us the false value. Please provide the real URL to the wiki, current URL redirects to {}".format(
					request.url))
		elif 399 < request.status_code < 500:
			logger.error("Request returned ClientError status code on {url}".format(url=request.url))
			self.statistics.update(Log(type=LogType.HTTP_ERROR, title="{} error".format(request.status_code), details=str(request.headers) + "\n" + str(request.url)))
			raise ClientError(request)
		else:
			try:
				request_json = self.parse_mw_request_info(request.json(), request.url)
				for item in json_path:
					request_json = request_json[item]
			except ValueError:
				logger.warning("ValueError when extracting JSON data on {url}".format(url=request.url))
				raise ServerError
			except MediaWikiError:
				logger.exception("MediaWiki error on request: {}".format(request.url))
				raise
			except KeyError:
				logger.exception("KeyError while iterating over json_path, full response: {}".format(request.json()))
				raise
		return request_json

	async def fetch_wiki(self, amount=10) -> dict:
		if self.mw_messages is None:
			params = OrderedDict({"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
					  "meta": "allmessages|siteinfo",
					  "utf8": 1, "tglimit": "max", "tgprop": "displayname",
					  "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user|userid",
					  "rclimit": amount, "rcshow": "!bot", "rctype": "edit|new|log|categorize",
					  "ammessages": "recentchanges-page-added-to-category|recentchanges-page-removed-from-category|recentchanges-page-added-to-category-bundled|recentchanges-page-removed-from-category-bundled",
					  "amenableparser": 1, "amincludelocal": 1, "siprop": "namespaces|general"})
		else:
			params = OrderedDict({"action": "query", "format": "json", "uselang": "content", "list": "tags|recentchanges",
					  "meta": "siteinfo", "utf8": 1, "rcshow": "!bot",
					  "rcprop": "title|redirect|timestamp|ids|loginfo|parsedcomment|sizes|flags|tags|user|userid",
					  "rclimit": amount, "rctype": "edit|new|log|categorize", "siprop": "namespaces|general"})
		try:
			response = await self.api_request(params=params)
		except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError) as e:
			logger.error("A connection error occurred while requesting {}".format(params))
			raise WikiServerError(e)
		return response

	async def scan(self, amount=10):
		"""Main track of fetching RecentChanges of a wiki.

		:raises WikiServerError
		"""
		while True:  # Trap event in case there are more changes needed to be fetched
			try:
				request = await self.fetch_wiki(amount=amount)
				self.client.last_request = request
			except WikiServerError as e:
				# If WikiServerError comes up 2 times in recent 2 minutes, this will reraise the exception, otherwise waits 2 seconds and retries
				self.statistics.update(Log(type=LogType.CONNECTION_ERROR, title=str(e.exception)))
				if self.statistics.recent_connection_errors() > 9:
					raise
				await asyncio.sleep(2.0)
				continue
			if not self.mw_messages or self.recache_requested:
				process_cachable(request, self)
			try:
				recent_changes = request["query"]["recentchanges"]
				recent_changes.reverse()
			except KeyError:
				raise WikiError
			if self.rc_id in (0, None, -1):
				if len(recent_changes) > 0:
					self.statistics.update(last_action=recent_changes[-1]["rcid"])
					dbmanager.add(("UPDATE rcgcdb SET rcid = $1 WHERE wiki = $2 AND ( rcid != -1 OR rcid IS NULL )",
								   (recent_changes[-1]["rcid"], self.script_url)))
				else:
					self.statistics.update(last_action=0)
					dbmanager.add(("UPDATE rcgcdb SET rcid = 0 WHERE wiki = $1 AND ( rcid != -1 OR rcid IS NULL )", (self.script_url)))
				return   # TODO Add a log entry?
			categorize_events = {}
			new_events = 0
			self.statistics.last_checked_rc = int(time.time())
			highest_id = self.rc_id
			old_highest_id = self.rc_id
			for change in recent_changes:
				if change["rcid"] > highest_id and amount != 450:
					new_events += 1
					if new_events == 10:
						# call the function again with max limit for more results, ignore the ones in this request
						logger.debug("There were too many new events, queuing wiki with 450 limit.")
						amount = 450
						break
				await process_cats(change, self, categorize_events)
			else:  # adequate amount of changes
				message_list = []  # Collect all messages so they can be efficiently merged in Discord message sender
				for change in recent_changes:  # Yeah, second loop since the categories require to be all loaded up
					if change["rcid"] > self.rc_id:
						if highest_id is None or change["rcid"] > highest_id:  # make sure that the highest_rc is really highest rcid but do allow other entries with potentially lesser rcids come after without breaking the cycle
							highest_id = change["rcid"]
						for combination, webhooks in self.rc_targets.items():
							message = await rc_processor(self, change, categorize_events.get(change.get("revid"), None), combination, webhooks)
							if message is None:
								break
							message.wiki = self
							message_list.append(QueueEntry(message, webhooks, self))
				messagequeue.add_messages(message_list)
				if old_highest_id != highest_id:  # update only when differs
					self.statistics.update(last_action=highest_id)
					dbmanager.add(("UPDATE rcgcdb SET rcid = $1 WHERE wiki = $2 AND ( rcid != -1 OR rcid IS NULL )", (highest_id, self.script_url)))  # If this is not enough for the future, save rcid in message sending function to make sure we always send all of the changes
				return

	async def remove_webhook_from_db(self, reason: str):
		raise NotImplementedError

	async def remove_wiki_from_db(self, reason: str):
		raise NotImplementedError  # TODO

	async def fetch_discussions(self, params: dict) -> tuple[aiohttp.ClientResponse, dict]:
		header = settings["header"]
		header["Accept"] = "application/hal+json"
		async with aiohttp.ClientSession(headers=header,
										 timeout=aiohttp.ClientTimeout(6.0)) as session:
			url_path = "{wiki}wikia.php".format(wiki=self.script_url)
			try:
				feeds_response = await session.get(url_path, params=params)
				feeds_response.raise_for_status()
			except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError,
					aiohttp.ClientResponseError, aiohttp.TooManyRedirects) as e:
				logger.error("A connection error occurred while requesting {}".format(feeds_response.url))
				raise WikiServerError(e)
			return feeds_response, await feeds_response.json(encoding="UTF-8")

	def pull_comment(self, comment_id):
		try:
			comment = self.sync_api_request("?action=comment&do=getRaw&comment_id={comment}&format=json".format(comment=comment_id), "text")
			logger.debug("Got the following comment from the API: {}".format(comment))
		except (ServerError, MediaWikiError):
			pass
		except (BadRequest, ClientError):
			logger.exception("Some kind of issue while creating a request (most likely client error).")
		except KeyError:
			logger.exception("CurseProfile extension API did not respond with a valid comment content.")
		else:
			if len(comment) > 1000:
				comment = comment[0:1000] + "…"
			return comment
		return ""


def process_cachable(response: dict, wiki_object: Wiki) -> None:
	"""This function processes cachable objects – such as MediaWiki system messages and wiki tag display names to be used
	for processing of DiscordMessages and saves them in a wiki object."""
	mw_messages = response.get("query", {}).get("allmessages", [])
	final_mw_messages = dict()
	for msg in mw_messages:
		if "missing" not in msg:  # ignore missing strings
			final_mw_messages[msg["name"]] = re.sub(r'\[\[.*?]]', '', msg["*"])
		else:
			logger.warning("Could not fetch the MW message translation for: {}".format(msg["name"]))
	wiki_object.mw_messages = MWMessages(final_mw_messages)
	for tag in response["query"]["tags"]:
		try:
			wiki_object.tags[tag["name"]] = (BeautifulSoup(tag["displayname"], "lxml")).get_text()
		except KeyError:
			wiki_object.tags[tag["name"]] = None
	wiki_object.namespaces = response["query"]["namespaces"]
	wiki_object.recache_requested = False


async def rc_processor(wiki: Wiki, change: dict, changed_categories: dict, display_options: namedtuple("Settings", ["lang", "display", "buttons"]), webhooks: list) -> Optional[DiscordMessage]:
	"""This function takes more vital information, communicates with a formatter and constructs DiscordMessage with it.
	It creates DiscordMessageMetadata object, LinkParser and Context. Prepares a comment """
	from src.misc import LinkParser
	LinkParser = LinkParser(wiki.client.WIKI_JUST_DOMAIN)
	metadata = DiscordMessageMetadata("POST", rev_id=change.get("revid", None), log_id=change.get("logid", None),
													page_id=change.get("pageid", None), message_display=display_options.display)
	context = Context("embed" if display_options.display > 0 else "compact", "recentchanges", webhooks, wiki.client,
					  langs[display_options.lang]["formatters"], prepare_settings(display_options.display), display_options.buttons)
	if ("actionhidden" in change or "suppressed" in change) and "suppressed" not in settings["ignored"]:  # if event is hidden using suppression
		context.event = "suppressed"
		run_hooks(pre_hooks, context, change)
		try:
			discord_message: Optional[DiscordMessage] = await asyncio.get_event_loop().run_in_executor(
				None, functools.partial(default_message("suppressed", context.message_type, formatter_hooks), context, change))
		except:
			if settings.get("error_tolerance", 1) > 0:
				discord_message: Optional[DiscordMessage] = None  # It's handled by send_to_discord, we still want other code to run
			else:
				raise
	else:
		if "commenthidden" not in change:
			LinkParser.feed(change.get("parsedcomment", ""))
			parsed_comment = LinkParser.new_string
		else:
			parsed_comment = langs[display_options.lang]["wiki"].gettext("~~hidden~~")
		if not parsed_comment and context.message_type == "embed" and settings["appearance"].get("embed", {}).get(
				"show_no_description_provided", True):
			parsed_comment = langs[display_options.lang]["wiki"].gettext("No description provided")
		context.set_parsedcomment(parsed_comment)
		if "userhidden" in change:
			change["user"] = langs[display_options.lang]["wiki"].gettext("hidden")
		if change.get("ns", -1) in settings.get("ignored_namespaces", ()):
			return
		if change["type"] in ["edit", "new"]:
			logger.debug("List of categories in essential_info: {}".format(changed_categories))
			identification_string = change["type"]
			context.set_categories(changed_categories)
		elif change["type"] == "categorize":
			return
		elif change["type"] == "log":
			identification_string = "{logtype}/{logaction}".format(logtype=change["logtype"],
																   logaction=change["logaction"])
		else:
			identification_string = change.get("type", "unknown")  # If event doesn't have a type
		if identification_string in settings["ignored"]:
			return
		context.event = identification_string
		try:
			discord_message: Optional[DiscordMessage] = await asyncio.get_event_loop().run_in_executor(None,
				functools.partial(default_message(identification_string, context.message_type, formatter_hooks), context,
								  change))
		except:
			if settings.get("error_tolerance", 1) > 0:
				discord_message: Optional[DiscordMessage] = None  # It's handled by send_to_discord, we still want other code to run
			else:
				raise
		if identification_string in ("delete/delete", "delete/delete_redir"):  # TODO Move it into a hook?
			wiki.delete_messages(dict(page_id=change.get("pageid")))
		elif identification_string == "delete/event":
			logparams = change.get('logparams', {"ids": []})
			if context.message_type == "embed":
				wiki.redact_messages(context, logparams.get("ids", []), "log_id", logparams.get("new", {}))
			else:
				for logid in logparams.get("ids", []):
					wiki.delete_messages(dict(logid=logid))
		elif identification_string == "delete/revision":
			logparams = change.get('logparams', {"ids": []})
			if context.message_type == "embed":
				wiki.redact_messages(context, logparams.get("ids", []), "rev_id", logparams.get("new", {}))
				if display_options.display == 3:
					wiki.redact_messages(context, wiki.find_middle_next(logparams.get("ids", []), change.get("pageid", -1)), "rev_id",
									{"content": ""})
			else:
				for revid in logparams.get("ids", []):
					wiki.delete_messages(dict(revid=revid))
	run_hooks(post_hooks, discord_message, metadata, context, change)
	if discord_message:  # TODO How to react when none? (crash in formatter), probably bad handling atm
		discord_message.finish_embed()
		discord_message.metadata = metadata
	return discord_message


async def process_cats(event: dict, local_wiki: Wiki, categorize_events: dict):
	"""Process categories based on local MW messages. """
	if event["type"] == "categorize":
		if "commenthidden" not in event:
			if local_wiki.mw_messages is not None:
				cat_title = event["title"].split(':', 1)[1]
				# I so much hate this, blame Markus for making me do this
				if event["revid"] not in categorize_events:
					categorize_events[event["revid"]] = {"new": set(), "removed": set()}
				comment_to_match = re.sub(r'<.*?a>', '', event["parsedcomment"])
				if local_wiki.mw_messages["recentchanges-page-added-to-category"] in comment_to_match or local_wiki.mw_messages["recentchanges-page-added-to-category-bundled"] in comment_to_match:  # Added to category
					categorize_events[event["revid"]]["new"].add(cat_title)
					#logger.debug("Matched {} to added category for {}".format(cat_title, event["revid"]))
				elif local_wiki.mw_messages["recentchanges-page-removed-from-category"] in comment_to_match or local_wiki.mw_messages["recentchanges-page-removed-from-category-bundled"] in comment_to_match:  # Removed from category
					categorize_events[event["revid"]]["removed"].add(cat_title)
					#logger.debug("Matched {} to removed category for {}".format(cat_title, event["revid"]))
				else:
					logger.debug(
						"Unknown match for category change with messages {} and comment_to_match {}".format(local_wiki.mw_messages,comment_to_match))
			else:
				logger.warning(
					"Init information not available, could not read category information. Please restart the bot.")
		else:
			logger.debug("Log entry got suppressed, ignoring entry.")

# This function has been removed. While its implementation seems sound, it should be considered only if we find performance
# concerns with RcGcDb
# async def process_mwmsgs(wiki_response: dict, local_wiki: Wiki, mw_msgs: dict):
# 	"""
# 	This function is made to parse the initial wiki extended information to update local_wiki.mw_messages that stores the key
# 	to mw_msgs that is a dict storing id: tuple where tuple is a set of MW messages for categories.
# 	The reason it's constructed this way is to prevent duplication of data in memory so Markus doesn't complain about
# 	high RAM usage. It does however affect CPU performance as every wiki requires to check the list for the matching
# 	tuples of MW messages.
#
# 	:param wiki_response:
# 	:param local_wiki:
# 	:param mw_msgs:
# 	:return:
# 	"""
# 	msgs = []
# 	for message in wiki_response["query"]["allmessages"]:
# 		if not "missing" in message:  # ignore missing strings
# 			msgs.append((message["name"], re.sub(r'\[\[.*?\]\]', '', message["*"])))
# 		else:
# 			logger.warning("Could not fetch the MW message translation for: {}".format(message["name"]))
# 	msgs = tuple(msgs)
# 	for key, set in mw_msgs.items():
# 		if msgs == set:
# 			local_wiki.mw_messages = key
# 			return
# 	# if same entry is not in mw_msgs
# 	key = len(mw_msgs)
# 	mw_msgs[key] = msgs  # it may be a little bit messy for sure, however I don't expect any reason to remove mw_msgs entries by one
# 	local_wiki.mw_messages = key
