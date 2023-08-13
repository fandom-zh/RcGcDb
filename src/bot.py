import aiohttp
import asyncio
import logging.config
import signal
import sys
import nest_asyncio
import time
from collections import defaultdict, namedtuple
from typing import Generator
import importlib
from contextlib import asynccontextmanager

from src.discussions import Discussions
from src.discord.queue import messagequeue
from src.argparser import command_line_args
from src.config import settings
from src.database import db
from src.exceptions import *
from src.queue_handler import dbmanager
from src.wiki import Wiki, process_cats
from src.domain_manager import domains


logging.config.dictConfig(settings["logging"])
logger = logging.getLogger("rcgcdb.bot")
logger.debug("Current settings: {settings}".format(settings=settings))
logger.info("RcGcDb v{} is starting up.".format("2.0"))

if command_line_args.debug:
    logger.info("Debug mode is active!")

# Log Fail states with structure wiki_url: number of fail states
all_wikis: dict = {}

main_tasks: dict = {}

# First populate the all_wikis list with every wiki
# Reasons for this: 1. we require amount of wikis to calculate the cooldown between requests
# 2. Easier to code


def load_extensions():
    """Loads all of the extensions, can be a local import because all we need is them to register"""
    try:
        importlib.import_module(settings.get('extensions_dir', 'extensions'), 'extensions')
    except ImportError:
        logger.critical("No extensions module found. What's going on?")
        logger.exception("Error:")
        sys.exit(1)


async def populate_wikis():
    logger.info("Populating domain manager with wikis...")
    start = time.time()
    async with db.pool().acquire() as connection:
        async with connection.transaction():
            async for db_wiki in connection.cursor('select wiki, MAX(rcid) AS rcid, MAX(postid) AS postid from rcgcdw group by wiki;'):
                print(db_wiki)
                try:
                    await domains.new_wiki(Wiki(db_wiki["wiki"], db_wiki["rcid"], db_wiki["postid"]))
                except WikiExists:  # Can rarely happen when Pub/Sub registers wiki before population
                    pass
    logger.info("Populating domain manager with wikis took {} seconds".format(time.time()-start))


async def message_sender():
    """message_sender is a coroutine responsible for handling Discord messages and their sending to Discord"""
    try:
        while True:
            await messagequeue.resend_msgs()
            if main_tasks["msg_queue_shield"].cancelled():
                raise asyncio.CancelledError
    except asyncio.CancelledError:
        while len(messagequeue):
            logger.info("Shutting down after sending {} more Discord messages...".format(len(messagequeue)))
            await messagequeue.resend_msgs()
        pass
    except:
        if command_line_args.debug:
            logger.exception("Exception on DC message sender")
            shutdown(loop=asyncio.get_event_loop())
        else:
            logger.exception("Exception on DC message sender")
            # await generic_msg_sender_exception_logger(traceback.format_exc(), "Message sender exception")  # TODO


# async def discussion_handler():
#     await asyncio.sleep(3.0)  # Make some time before IRC code is executed, happens only once and saves if inside
#     try:
#         while True:
#             async with db.pool().acquire() as connection:
#                 async with connection.transaction():
#                     async for db_wiki in connection.cursor("SELECT DISTINCT wiki, rcid, postid FROM rcgcdw WHERE postid != '-1' OR postid IS NULL"):
#                         try:
#                             local_wiki = all_wikis[db_wiki["wiki"]]  # set a reference to a wiki object from memory
#                         except KeyError:
#                             local_wiki = all_wikis[db_wiki["wiki"]] = Wiki()
#                             local_wiki.rc_active = db_wiki["rcid"]
#                         if db_wiki["wiki"] not in rcqueue.irc_mapping["fandom.com"].updated_discussions and \
#                                 local_wiki.last_discussion_check+settings["irc_overtime"] > time.time():  # I swear if another wiki farm ever starts using Fandom discussions I'm gonna use explosion magic
#                             continue
#                         else:
#                             try:
#                                 rcqueue.irc_mapping["fandom.com"].updated_discussions.remove(db_wiki["wiki"])
#                             except KeyError:
#                                 pass  # to be expected
#                         header = settings["header"]
#                         header["Accept"] = "application/hal+json"
#                         async with aiohttp.ClientSession(headers=header,
#                                                          timeout=aiohttp.ClientTimeout(6.0)) as session:
#                             try:
#                                 feeds_response = await local_wiki.fetch_feeds(db_wiki["wiki"], session)
#                             except (WikiServerError, WikiError):
#                                 continue  # ignore this wiki if it throws errors
#                             try:
#                                 discussion_feed_resp = await feeds_response.json(encoding="UTF-8")
#                                 if "error" in discussion_feed_resp:
#                                     error = discussion_feed_resp["error"]
#                                     if error == "NotFoundException":  # Discussions disabled
#                                         if db_wiki["rcid"] != -1:  # RC feed is disabled
#                                             await connection.execute("UPDATE rcgcdw SET postid = $1 WHERE wiki = $2", "-1", db_wiki["wiki"])
#                                         else:
#                                             await local_wiki.remove(db_wiki["wiki"], 1000)
#                                         continue
#                                     raise WikiError
#                                 discussion_feed = discussion_feed_resp["_embedded"]["doc:posts"]
#                                 discussion_feed.reverse()
#                             except aiohttp.ContentTypeError:
#                                 logger.exception("Wiki seems to be resulting in non-json content.")
#                                 continue
#                             except asyncio.TimeoutError:
#                                 logger.debug("Timeout on reading JSON of discussion post feeed.")
#                                 continue
#                             except:
#                                 logger.exception("On loading json of response.")
#                                 continue
#                         if db_wiki["postid"] is None:  # new wiki, just get the last post to not spam the channel
#                             if len(discussion_feed) > 0:
#                                 DBHandler.add(db_wiki["wiki"], discussion_feed[-1]["id"], True)
#                             else:
#                                 DBHandler.add(db_wiki["wiki"], "0", True)
#                             continue
#                         comment_events = []
#                         targets = await generate_targets(db_wiki["wiki"], "AND NOT postid = '-1'")
#                         for post in discussion_feed:
#                             if post["_embedded"]["thread"][0]["containerType"] == "ARTICLE_COMMENT" and post["id"] > db_wiki["postid"]:
#                                 comment_events.append(post["forumId"])
#                         comment_pages: dict = {}
#                         if comment_events:
#                             try:
#                                 comment_pages = await local_wiki.safe_request(
#                                     "{wiki}wikia.php?controller=FeedsAndPosts&method=getArticleNamesAndUsernames&stablePageIds={pages}&format=json".format(
#                                         wiki=db_wiki["wiki"], pages=",".join(comment_events)
#                                     ), RateLimiter(), "articleNames")
#                             except aiohttp.ClientResponseError:  # Fandom can be funny sometimes... See #30
#                                 comment_pages = None
#                             except:
#                                 if command_line_args.debug:
#                                     logger.exception("Exception on Feeds article comment request")
#                                     shutdown(loop=asyncio.get_event_loop())
#                                 else:
#                                     logger.exception("Exception on Feeds article comment request")
#                                     await generic_msg_sender_exception_logger(traceback.format_exc(),
#                                                                               "Exception on Feeds article comment request",
#                                                                               Post=str(post)[0:1000], Wiki=db_wiki["wiki"])
#                         message_list = defaultdict(list)
#                         for post in discussion_feed:  # Yeah, second loop since the comments require an extra request
#                             if post["id"] > db_wiki["postid"]:
#                                 for target in targets.items():
#                                     try:
#                                         message = await essential_feeds(post, comment_pages, db_wiki, target)
#                                         if message is not None:
#                                             message_list[target[0]].append(message)
#                                     except asyncio.CancelledError:
#                                         raise
#                                     except:
#                                         if command_line_args.debug:
#                                             logger.exception("Exception on Feeds formatter")
#                                             shutdown(loop=asyncio.get_event_loop())
#                                         else:
#                                             logger.exception("Exception on Feeds formatter")
#                                             await generic_msg_sender_exception_logger(traceback.format_exc(), "Exception in feed formatter", Post=str(post)[0:1000], Wiki=db_wiki["wiki"])
#                         # Lets stack the messages
#                         for messages in message_list.values():
#                             messages = stack_message_list(messages)
#                             for message in messages:
#                                 await send_to_discord(message)
#                         if discussion_feed:
#                             DBHandler.add(db_wiki["wiki"], post["id"], True)
#                         await asyncio.sleep(delay=2.0)  # hardcoded really doesn't need much more
#             await asyncio.sleep(delay=1.0) # Avoid lock on no wikis
#     except asyncio.CancelledError:
#         pass
#     except:
#         if command_line_args.debug:
#             raise  # reraise the issue
#         else:
#             logger.exception("Exception on Feeds formatter")
#             await generic_msg_sender_exception_logger(traceback.format_exc(), "Discussion handler task exception", Wiki=db_wiki["wiki"])


def shutdown(loop, signal=None):
    global main_tasks
    loop.remove_signal_handler(signal)
    if len(messagequeue) > 0:
        logger.warning("Some messages are still queued!")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(main_tasks["message_sender"])
        loop.run_until_complete(main_tasks["database_updates"])
    for task in asyncio.all_tasks(loop):
        logger.debug("Killing task")
        task.cancel()
    try:
        loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop)))
    except asyncio.CancelledError:
        loop.stop()
        logger.info("Script has shut down due to signal {}.".format(signal))
    logging.shutdown()
    # sys.exit(0)


# def global_exception_handler(loop, context):
# 	"""Global exception handler for asyncio, lets us know when something crashes"""
# 	msg = context.get("exception", context["message"])
# 	logger.error("Global exception handler: {}".format(msg))
# 	if command_line_args.debug is False:
# 		requests.post("https://discord.com/api/webhooks/"+settings["monitoring_webhook"], data=repr(DiscordMessage("compact", "monitoring", [settings["monitoring_webhook"]], wiki=None, content="[RcGcDb] Global exception handler: {}".format(msg))), headers={'Content-Type': 'application/json'})
# 	else:
# 		shutdown(loop)


async def main_loop():
    global main_tasks
    # Fix some asyncio problems
    loop = asyncio.get_event_loop()
    nest_asyncio.apply(loop)
    # Setup database connection
    await db.setup_connection()
    await db.create_pubsub_interface(domains.webhook_update)
    logger.debug("Connection type: {}".format(db.connection_pool))
    load_extensions()
    await populate_wikis()
    # START LISTENER CONNECTION
    domains.run_all_domains()
    discussions = Discussions(domains.return_domain("fandom.com") if domains.check_for_domain("fandom.com") else None)
    try:
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            loop.add_signal_handler(
                s, lambda s=s: shutdown(loop, signal=s))
    except AttributeError:
        logger.info("Running on Windows, some things may not work as they should.")
        signals = (signal.SIGBREAK, signal.SIGTERM, signal.SIGINT)
    # loop.set_exception_handler(global_exception_handler)
    try:
        main_tasks = {"message_sender": asyncio.create_task(message_sender()),
                      "database_updates": asyncio.create_task(dbmanager.update_db()),
                      "fandom_discussions": asyncio.create_task(discussions.tick_discussions())}  # "discussion_handler": asyncio.create_task(discussion_handler()),
        main_tasks["msg_queue_shield"] = asyncio.shield(main_tasks["message_sender"])
        main_tasks["database_updates_shield"] = asyncio.shield(main_tasks["database_updates"])
        await asyncio.gather(main_tasks["message_sender"], main_tasks["database_updates"])
    except KeyboardInterrupt:
        shutdown(loop)
    except asyncio.CancelledError:
        return

asyncio.run(main_loop(), debug=command_line_args.debug)
