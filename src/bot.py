import logging.config
from src.config import settings

logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))

# Fetch basic information about all of the wikis in the database



# Start queueing logic

