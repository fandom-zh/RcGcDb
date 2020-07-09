import logging.config
from src.config import settings
import sqlite3
from src.wiki import Wiki

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))

conn = sqlite3.connect('rcgcdb.db')
c = conn.cursor()

# Fetch basic information about all of the wikis in the database
all_wikis = {}

for wiki in c.execute('SELECT * FROM wikis'):
	all_wikis[wiki[0]] = Wiki()  # assign cached information


# Start queueing logic

