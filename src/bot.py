import logging.config
from src.config import settings
import sqlite3
from src.wiki import Wiki
import asyncio, aiohttp

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))

conn = sqlite3.connect('rcgcdb.db')
c = conn.cursor()

# Log Fail states with structure wiki_id: number of fail states
all_wikis = {}
mw_msgs = {}  # will have the type of id: tuple

# First populate the all_wikis list with every wiki
# Reasons for this: 1. we require amount of wikis to calculate the cooldown between requests
# 2. Easier to code

for wiki in c.execute('SELECT ROWID, * FROM wikis'):
	all_wikis[wiki[0]] = Wiki()

# Start queueing logic

async def main_loop():
	for db_wiki in c.execute('SELECT ROWID, * FROM wikis'):
		extended = False
		if wiki[0] not in all_wikis:
			logger.debug("New wiki: {}".format(wiki[1]))
			all_wikis[wiki[0]] = Wiki()
		local_wiki = all_wikis[wiki[0]]  # set a reference to a wiki object from memory
		if all_wikis[wiki[0]].mw_messages is None:
			extended = True
		wiki_response = await local_wiki.fetch_wiki(extended)
		try:
			await local_wiki.check_status(wiki[0], wiki_response.status, db_wiki[1])
		except: