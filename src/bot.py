import aiohttp
import asyncio
import logging.config
import signal
import sys
import traceback
from collections import defaultdict

import functools
import requests

from contextlib import asynccontextmanager
from src.argparser import command_line_args
from src.config import settings
from src.database import db_cursor
from src.exceptions import *
from src.misc import get_paths, get_domain
from src.msgqueue import messagequeue
from src.queue_handler import DBHandler
from src.wiki import Wiki, process_cats, process_mwmsgs, essential_info, essential_feeds
from src.discord import DiscordMessage, formatter_exception_logger, msg_sender_exception_logger, \
	group_task_exception_logger, discussion_task_exception_logger
from src.wiki_ratelimiter import RateLimiter

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))
logger.info("RcGcDb v{} is starting up.".format("1.0"))

if command_line_args.debug:
	logger.info("Debug mode is active!")

# Log Fail states with structure wiki_url: number of fail states
all_wikis: dict = {}
mw_msgs: dict = {}  # will have the type of id: tuple

# First populate the all_wikis list with every wiki
# Reasons for this: 1. we require amount of wikis to calculate the cooldown between requests
# 2. Easier to code

queue_limit = settings.get("queue_limit", 30)

class LimitedList(list):
	def __init__(self, *args):
		list.__init__(self, *args)

	def append(self, object) -> None:
		if len(self) < queue_limit:
			self.insert(len(self), object)
			return
		raise ListFull


class RcQueue:
	def __init__(self):
		self.domain_list = {}
		self.to_remove = []

	async def start_group(self, group, initial_wikis):
		"""Starts a task for given domain group"""
		if group not in self.domain_list:
			self.domain_list[group] = {"task": asyncio.create_task(scan_group(group), name=group), "last_rowid": 0, "query": LimitedList(initial_wikis), "rate_limiter": RateLimiter()}
		else:
			raise KeyError

	async def remove_wiki_from_group(self, wiki):
		"""Removes a wiki from query of given domain group"""
		group = get_domain(wiki)
		self[group]["query"] = [x for x in self[group]["query"] if x["wiki"] == wiki]
		if not self[group]["query"]:  # if there is no wiki left in the queue, get rid of the task
			self[group]["task"].cancel()
			del self.domain_list[group]

	@asynccontextmanager
	async def retrieve_next_queued(self, group):
		"""Retrives next wiki in the queue for given domain"""
		try:
			yield self.domain_list[group]["query"][0]
		except:
			if command_line_args.debug:
				logger.exception("RC Group exception")
				raise  # reraise the issue
			else:
				logger.exception("Group task returned error")
				await group_task_exception_logger(group, traceback.format_exc())
		else:
			self.domain_list[group]["query"].pop(0)


	async def update_queues(self):
		"""Makes a round on rcgcdw DB and looks for updates to the queues in self.domain_list"""
		try:
			fetch_all = db_cursor.execute(
				'SELECT ROWID, webhook, wiki, lang, display, wikiid, rcid FROM rcgcdw WHERE NOT rcid = -1 GROUP BY wiki ORDER BY ROWID')
			self.to_remove = list(all_wikis.keys())  # first populate this list and remove wikis that are still in the db, clean up the rest
			full = []
			for db_wiki in fetch_all.fetchall():
				domain = get_domain(db_wiki["wiki"])
				current_domain = self[domain]
				try:
					if not db_wiki["ROWID"] < current_domain["last_rowid"]:
						current_domain["query"].append(db_wiki)
					self.to_remove.remove(db_wiki["wiki"])
				except KeyError:
					await self.start_group(domain, db_wiki)
					logger.info("A new domain group has been added since last time, adding it to the domain_list and starting a task...")
				except ListFull:
					full.append(domain)
					current_domain["last_rowid"] = db_wiki["ROWID"]
					continue
			for wiki in self.to_remove:
				del all_wikis[wiki]
				await self.remove_wiki_from_group(wiki)
			for group, data in self.domain_list.items():
				if group not in full:
					self[group]["last_rowid"] = 0  # iter reached the end without being stuck on full list
		except:
			logger.exception("Queue error!")

	def __getitem__(self, item):
		"""Returns the query of given domain group"""
		return self.domain_list[item]

	def __setitem__(self, key, value):
		self.domain_list[key] = value


rcqueue = RcQueue()


# Start queueing logic

def calculate_delay_for_group(group_length: int) -> float:
	"""Calculate the delay between fetching each wiki to avoid rate limits"""
	min_delay = 60 / settings["max_requests_per_minute"]
	if (group_length * min_delay) < settings["minimal_cooldown_per_wiki_in_sec"]:
		return settings["minimal_cooldown_per_wiki_in_sec"] / group_length
	else:
		return 0.0


def generate_targets(wiki_url: str) -> defaultdict:
	"""To minimize the amount of requests, we generate a list of language/display mode combinations to create messages for
	this way we can send the same message to multiple webhooks which have the same wiki and settings without doing another
	request to the wiki just to duplicate the message.
	"""
	combinations = defaultdict(list)
	for webhook in db_cursor.execute('SELECT webhook, lang, display FROM rcgcdw WHERE wiki = ?', (wiki_url,)):
		combination = (webhook["lang"], webhook["display"])
		combinations[combination].append(webhook["webhook"])
	return combinations


async def generate_domain_groups():
	"""Generate a list of wikis per domain (fandom.com, wikipedia.org etc.)"""
	domain_wikis = defaultdict(list)
	fetch_all = db_cursor.execute('SELECT ROWID, webhook, wiki, lang, display, wikiid, rcid FROM rcgcdw WHERE NOT rcid = -1 GROUP BY wiki ORDER BY ROWID ASC')
	for db_wiki in fetch_all.fetchall():
		domain_wikis[get_domain(db_wiki["wiki"])].append(db_wiki)
		all_wikis[db_wiki["wiki"]] = Wiki()  # populate all_wikis
	for group, db_wikis in domain_wikis.items():
		yield group, db_wikis


async def scan_group(group: str):
	rate_limiter = rcqueue[group]["rate_limiter"]
	while True:
		async with rcqueue.retrieve_next_queued(group) as db_wiki:  # acquire next wiki in queue
			logger.debug("Wiki {}".format(db_wiki["wiki"]))
			local_wiki = all_wikis[db_wiki["wiki"]]  # set a reference to a wiki object from memory
			extended = False
			if local_wiki.mw_messages is None:
				extended = True
			async with aiohttp.ClientSession(headers=settings["header"],
			                                 timeout=aiohttp.ClientTimeout(3.0)) as session:
				try:
					wiki_response = await local_wiki.fetch_wiki(extended, db_wiki["wiki"], session, rate_limiter)
					await local_wiki.check_status(db_wiki["wiki"], wiki_response.status)
				except (WikiServerError, WikiError):
					logger.error("Exeption when fetching the wiki")
					continue  # ignore this wiki if it throws errors
				try:
					recent_changes_resp = await wiki_response.json()
					if "error" in recent_changes_resp or "errors" in recent_changes_resp:
						error = recent_changes_resp.get("error", recent_changes_resp["errors"])
						if error["code"] == "readapidenied":
							await local_wiki.fail_add(db_wiki["wiki"], 410)
							continue
						raise WikiError
					recent_changes = recent_changes_resp['query']['recentchanges']
					recent_changes.reverse()
				except aiohttp.ContentTypeError:
					logger.exception("Wiki seems to be resulting in non-json content.")
					await local_wiki.fail_add(db_wiki["wiki"], 410)
					continue
				except:
					logger.exception("On loading json of response.")
					continue
			if extended:
				await process_mwmsgs(recent_changes_resp, local_wiki, mw_msgs)
			if db_wiki["rcid"] is None:  # new wiki, just get the last rc to not spam the channel
				if len(recent_changes) > 0:
					DBHandler.add(db_wiki["wiki"], recent_changes[-1]["rcid"])
				else:
					DBHandler.add(db_wiki["wiki"], 0)
				DBHandler.update_db()
				continue
			categorize_events = {}
			targets = generate_targets(db_wiki["wiki"])
			paths = get_paths(db_wiki["wiki"], recent_changes_resp)
			for change in recent_changes:
				await process_cats(change, local_wiki, mw_msgs, categorize_events)
			for change in recent_changes:  # Yeah, second loop since the categories require to be all loaded up
				if change["rcid"] > db_wiki["rcid"]:
					for target in targets.items():
						try:
							await essential_info(change, categorize_events, local_wiki, db_wiki,
							                     target, paths, recent_changes_resp, rate_limiter)
						except:
							if command_line_args.debug:
								logger.exception("Exception on RC formatter")
								raise
							else:
								logger.exception("Exception on RC formatter")
								await formatter_exception_logger(db_wiki["wiki"], change, traceback.format_exc())
			if recent_changes:
				DBHandler.add(db_wiki["wiki"], change["rcid"])
		delay_between_wikis = calculate_delay_for_group(len(rcqueue[group]["query"]))
		await asyncio.sleep(delay_between_wikis)
		DBHandler.update_db()


async def wiki_scanner():
	"""Wiki scanner is spawned as a task which purpose is to continuously run over wikis in the DB, fetching recent changes
	to add messages based on the changes to message queue later handled by message_sender coroutine."""
	try:
		async for group, db_wikis in generate_domain_groups():  # First scan
			await rcqueue.start_group(group, db_wikis)
		while True:
			await asyncio.sleep(20.0)
			await rcqueue.update_queues()
	except asyncio.CancelledError:
		raise


async def message_sender():
	"""message_sender is a coroutine responsible for handling Discord messages and their sending to Discord"""
	try:
		while True:
			await messagequeue.resend_msgs()
	except:
		if command_line_args.debug:
			logger.exception("Exception on DC message sender")
			raise  # reraise the issue
		else:
			logger.exception("Exception on DC message sender")
			await msg_sender_exception_logger(traceback.format_exc())

async def discussion_handler():
	try:
		while True:
			fetch_all = db_cursor.execute(
				'SELECT ROWID, webhook, wiki, lang, display, wikiid, rcid, postid FROM rcgcdw WHERE NOT wikiid = ""')
			for db_wiki in fetch_all.fetchall():
				if db_wiki["wikiid"] is not None:
					header = settings["header"]
					header["Accept"] = "application/hal+json"
					async with aiohttp.ClientSession(headers=header,
					                                 timeout=aiohttp.ClientTimeout(3.0)) as session:
						local_wiki = all_wikis[db_wiki["wiki"]]  # set a reference to a wiki object from memory
						try:
							feeds_response = await local_wiki.fetch_feeds(db_wiki["wikiid"], session)
						except (WikiServerError, WikiError):
							logger.error("Exeption when fetching the wiki")
							continue  # ignore this wiki if it throws errors
						try:
							discussion_feed_resp = await feeds_response.json(encoding="UTF-8")
							if "title" in discussion_feed_resp:
								error = discussion_feed_resp["error"]
								if error == "site doesn't exists":
									db_cursor.execute("UPDATE rcgcdw SET wikiid = ? WHERE wiki = ?",
									                  (None, db_wiki["wiki"],))
									DBHandler.update_db()
									continue
								raise WikiError
							discussion_feed = discussion_feed_resp["_embedded"]["doc:posts"]
							discussion_feed.reverse()
						except aiohttp.ContentTypeError:
							logger.exception("Wiki seems to be resulting in non-json content.")
							continue
						except:
							logger.exception("On loading json of response.")
							continue
					if db_wiki["postid"] is None:  # new wiki, just get the last post to not spam the channel
						if len(discussion_feed) > 0:
							DBHandler.add(db_wiki["wiki"], discussion_feed[-1]["id"], True)
						else:
							DBHandler.add(db_wiki["wiki"], "0", True)
						DBHandler.update_db()
						continue
					targets = generate_targets(db_wiki["wiki"])
					for post in discussion_feed:
						if post["id"] > db_wiki["postid"]:
							for target in targets.items():
								try:
									await essential_feeds(post, db_wiki, target)
								except:
									if command_line_args.debug:
										raise  # reraise the issue
									else:
										logger.exception("Exception on Feeds formatter")
										await formatter_exception_logger(db_wiki["wiki"], post, traceback.format_exc())
					if discussion_feed:
						DBHandler.add(db_wiki["wiki"], post["id"], True)
				await asyncio.sleep(delay=2.0)  # hardcoded really doesn't need much more
			DBHandler.update_db()
	except:
		if command_line_args.debug:
			raise  # reraise the issue
		else:
			logger.exception("Exception on Feeds formatter")
			await discussion_task_exception_logger(db_wiki["wiki"], traceback.format_exc())



def shutdown(loop, signal=None):
	DBHandler.update_db()
	if len(messagequeue) > 0:
		logger.warning("Some messages are still queued!")
	loop.stop()
	logger.info("Script has shut down due to signal {}.".format(signal))
	for task in asyncio.all_tasks(loop):
		logger.debug("Killing task {}".format(task.get_name()))
		task.cancel()
	sys.exit(0)


def global_exception_handler(loop, context):
	"""Global exception handler for asyncio, lets us know when something crashes"""
	msg = context.get("exception", context["message"])
	logger.error("Global exception handler: {}".format(msg))
	if command_line_args.debug is False:
		requests.post("https://discord.com/api/webhooks/"+settings["monitoring_webhook"], data=repr(DiscordMessage("compact", "monitoring", [settings["monitoring_webhook"]], wiki=None, content="[RcGcDb] Global exception handler: {}".format(msg))), headers={'Content-Type': 'application/json'})
	else:
		shutdown(loop)


async def main_loop():
	loop = asyncio.get_event_loop()
	try:
		signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
		for s in signals:
			loop.add_signal_handler(
				s, lambda s=s: shutdown(loop, signal=s))
	except AttributeError:
		logger.info("Running on Windows, some things may not work as they should.")
		signals = (signal.SIGBREAK, signal.SIGTERM, signal.SIGINT)
	loop.set_exception_handler(global_exception_handler)
	try:
		task1 = asyncio.create_task(wiki_scanner())
		task2 = asyncio.create_task(message_sender())
		task3 = asyncio.create_task(discussion_handler())
		await task1
		await task2
		await task3
	except KeyboardInterrupt:
		shutdown(loop)


asyncio.run(main_loop(), debug=command_line_args.debug)
