import logging.config
from src.config import settings
import sqlite3
from src.wiki import Wiki, process_cats, process_mwmsgs, essential_info
import asyncio, aiohttp
from src.misc import get_paths
from src.exceptions import *
from src.database import db_cursor
from collections import defaultdict
from src.queue_handler import DBHandler
from src.msgqueue import messagequeue

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))

# Log Fail states with structure wiki_id: number of fail states
all_wikis: dict = {}
mw_msgs: dict = {}  # will have the type of id: tuple

# First populate the all_wikis list with every wiki
# Reasons for this: 1. we require amount of wikis to calculate the cooldown between requests
# 2. Easier to code

for wiki in db_cursor.execute('SELECT DISTINCT wiki FROM rcgcdw'):
	all_wikis[wiki] = Wiki()

# Start queueing logic


def calculate_delay() -> float:
	min_delay = 60/settings["max_requests_per_minute"]
	if (len(all_wikis) * min_delay) < settings["minimal_cooldown_per_wiki_in_sec"]:
		return settings["minimal_cooldown_per_wiki_in_sec"]/len(all_wikis)
	else:
		return min_delay


def generate_targets(wiki_url: str) -> defaultdict:
	combinations = defaultdict(list)
	for webhook in db_cursor.execute('SELECT ROWID, * FROM rcgcdw WHERE wiki = ?', (wiki_url,)):
		# rowid, guild, configid, webhook, wiki, lang, display, rcid, wikiid, postid
		combination = (webhook[5], webhook[6])  # lang, display
		combinations[combination].append(webhook[3])
	return combinations


async def wiki_scanner():
	while True:
		calc_delay = calculate_delay()
		fetch_all = db_cursor.execute('SELECT * FROM rcgcdw GROUP BY wiki')
		for db_wiki in fetch_all.fetchall():
			logger.debug("Wiki {}".format(db_wiki[3]))
			extended = False
			if db_wiki[3] not in all_wikis:
				logger.debug("New wiki: {}".format(db_wiki[3]))
				all_wikis[db_wiki[3]] = Wiki()
			local_wiki = all_wikis[db_wiki[3]]  # set a reference to a wiki object from memory
			if local_wiki.mw_messages is None:
				extended = True
			logger.debug("test")
			try:
				wiki_response = await local_wiki.fetch_wiki(extended, db_wiki[3])
				await local_wiki.check_status(db_wiki[3], wiki_response.status)
			except (WikiServerError, WikiError):
				logger.exception("Exeption when fetching the wiki")
				continue  # ignore this wiki if it throws errors
			try:
				recent_changes_resp = await wiki_response.json(encoding="UTF-8")
				recent_changes = recent_changes_resp['query']['recentchanges']
				recent_changes.reverse()
			except:
				logger.exception("On loading json of response.")
				continue
			if extended:
				await process_mwmsgs(recent_changes_resp, local_wiki, mw_msgs)
			if db_wiki[6] is None:  # new wiki, just get the last rc to not spam the channel
				if len(recent_changes) > 0:
					DBHandler.add(db_wiki[3], recent_changes[-1]["rcid"])
					continue
				else:
					DBHandler.add(db_wiki[3], 0)
					continue
			categorize_events = {}
			targets = generate_targets(db_wiki[3])
			paths = get_paths(db_wiki[3], recent_changes_resp)
			for change in recent_changes:
				await process_cats(change, local_wiki, mw_msgs, categorize_events)
			for change in recent_changes:  # Yeah, second loop since the categories require to be all loaded up
				if change["rcid"] > db_wiki[6]:
					for target in targets.items():
						await essential_info(change, categorize_events, local_wiki, db_wiki, target, paths, recent_changes_resp)
			if recent_changes:
				DBHandler.add(db_wiki[3], change["rcid"])
			DBHandler.update_db()
			await asyncio.sleep(delay=calc_delay)


async def message_sender():
	while True:
		await messagequeue.resend_msgs()



async def main_loop():
	task1 = asyncio.create_task(wiki_scanner())
	task2 = asyncio.create_task(message_sender())
	await task1
	await task2


asyncio.run(main_loop())
