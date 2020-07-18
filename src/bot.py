import logging.config
from src.config import settings
import sqlite3
from src.wiki import Wiki, process_cats, process_mwmsgs
import asyncio, aiohttp
from src.exceptions import *
from src.database import db_cursor
from queue_handler import DBHandler

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))

# Log Fail states with structure wiki_id: number of fail states
all_wikis: dict = {}
mw_msgs: dict = {}  # will have the type of id: tuple

# First populate the all_wikis list with every wiki
# Reasons for this: 1. we require amount of wikis to calculate the cooldown between requests
# 2. Easier to code

for wiki in db_cursor.execute('SELECT ROWID, * FROM wikis'):
	all_wikis[wiki[0]] = Wiki()

# Start queueing logic

def calculate_delay() -> float:
	min_delay = 60/settings["max_requests_per_minute"]
	if (len(all_wikis) * min_delay) < settings["minimal_cooldown_per_wiki_in_sec"]:
		return settings["minimal_cooldown_per_wiki_in_sec"]/len(all_wikis)
	else:
		return min_delay

async def main_loop():
	calc_delay = calculate_delay()

	for db_wiki in db_cursor.execute('SELECT ROWID, * FROM wikis'):
		extended = False
		if wiki[0] not in all_wikis:
			logger.debug("New wiki: {}".format(wiki[1]))
			all_wikis[wiki[0]] = Wiki()
		local_wiki = all_wikis[wiki[0]]  # set a reference to a wiki object from memory
		if local_wiki.mw_messages is None:
			extended = True
		try:
			wiki_response = await local_wiki.fetch_wiki(extended, db_wiki[3], db_wiki[4])
			await local_wiki.check_status(wiki[0], wiki_response.status, db_wiki[1])
		except (WikiServerError, WikiError):
			continue  # ignore this wiki if it throws errors
		try:
			recent_changes_resp = await wiki_response.json(encoding="UTF-8")
			recent_changes = recent_changes_resp['query']['recentchanges'].reverse()
		except:
			logger.exception("On loading json of response.")
			continue
		if extended:
			await process_mwmsgs(recent_changes_resp, local_wiki, mw_msgs)
		categorize_events = {}
		if db_wiki[6] is None:  # new wiki, just get the last rc to not spam the channel
			if len(recent_changes) > 0:
				DBHandler.add(db_wiki[0], recent_changes[-1]["rcid"])
				continue
			else:
				DBHandler.add(db_wiki[0], 0)
				continue
		for change in recent_changes:
			await process_cats(change, local_wiki, mw_msgs, categorize_events)
		for change in recent_changes:  # Yeah, second loop since the categories require to be all loaded up
			if change["rcid"] < db_wiki[6]:



		await asyncio.sleep(delay=calc_delay)
