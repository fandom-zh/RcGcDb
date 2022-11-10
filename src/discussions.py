from __future__ import annotations

import asyncio
import functools
import logging
import time
import typing
import aiohttp

from api.context import Context
from api.hooks import formatter_hooks
from api.util import default_message
from src.i18n import langs
from src.misc import prepare_settings
from src.exceptions import WikiError
from src.config import settings
from src.queue_handler import dbmanager
from src.argparser import command_line_args
from src.discord.message import DiscordMessageMetadata, DiscordMessage
from collections import OrderedDict, defaultdict
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.domain import Domain
    from src.wiki import Wiki, Settings

logger = logging.getLogger("rcgcdb.discussions")

class Discussions:
    def __init__(self, domain):
        self.domain_object: Optional[Domain] = domain

    async def tick_discussions(self):
        if self.domain_object is None:
            raise asyncio.CancelledError("fandom.com is not a domain we have any wikis for.")

        while True:
            try:
                wiki_url = self.domain_object.irc.updated_discussions.pop()
            except KeyError:
                break
            wiki = self.domain_object.get_wiki(wiki_url)
            if wiki is None:
                logger.error(f"Could not find a wiki with URL {wiki_url} in the domain group!")
                continue
            await self.run_discussion_scan(wiki)

        for wiki in self.filter_and_sort():
            if (int(time.time()) - wiki.statistics.last_checked_discussion) > settings.get("irc_overtime", 3600):
                await self.run_discussion_scan(wiki)
            else:
                return  # Recently scanned wikis will get at the end of the self.wikis, so we assume what is first hasn't been checked for a while

    def filter_and_sort(self) -> list[Wiki]:
        """Filters and sorts wikis from domain to return only the ones that aren't -1 and sorts them from oldest in checking to newest"""
        # return OrderedDict(sorted(filter(lambda wiki: wiki[1].discussion_id != -1, self.domain_object.wikis.items()), key=lambda wiki: wiki[1].statistics.last_checked_discussion))
        return sorted(filter(lambda wiki: wiki.discussion_id != -1, self.domain_object.wikis.values()), key=lambda wiki: wiki.statistics.last_checked_discussion)

    async def run_discussion_scan(self, wiki: Wiki):
        wiki.statistics.last_checked_discussion = int(time.time())
        params = {"controller": "DiscussionPost", "method": "getPosts", "includeCounters": "false",
                  "sortDirection": "descending", "sortKey": "creation_date", "limit": 20}
        feeds_response = await wiki.fetch_discussions(params)
        try:
            discussion_feed_resp = await feeds_response.json(encoding="UTF-8")
            if "error" in discussion_feed_resp:
                error = discussion_feed_resp["error"]
                if error == "NotFoundException":  # Discussions disabled
                    await dbmanager.add("UPDATE rcgcdw SET postid = $1 WHERE wiki = $2", "-1", wiki.script_url)
                    await dbmanager.update_db()
                    await wiki.update_targets()
                raise WikiError
            discussion_feed = discussion_feed_resp["_embedded"]["doc:posts"]
            discussion_feed.reverse()
        except aiohttp.ContentTypeError:
            logger.exception("Wiki seems to be resulting in non-json content.")
            return
        except asyncio.TimeoutError:
            logger.debug("Timeout on reading JSON of discussion post feed.")
            return
        if wiki.statistics.last_post is None:  # new wiki, just get the last post to not spam the channel
            if len(discussion_feed) > 0:
                dbmanager.add(("UPDATE rcgcdw SET postid = $1 WHERE wiki = $2 AND ( postid != -1 OR postid IS NULL )", (
                    discussion_feed[-1]["id"],
                    wiki.script_url)))
            else:
                dbmanager.add(wiki.script_url, "0", True)
            await dbmanager.update_db()
            return
        comment_events = []
        for post in discussion_feed:
            if post["_embedded"]["thread"][0]["containerType"] == "ARTICLE_COMMENT" and post["id"] > wiki.discussion_id:
                comment_events.append(post["forumId"])
        comment_pages: Optional[dict] = {}
        if comment_events:
            try:
                params = {"controller": "FeedsAndPosts", "method": "getArticleNamesAndUsernames",
                          "stablePageIds": ",".join(comment_events), "format": "json"}
                comment_pages_request = await wiki.fetch_discussions(params)
                comment_pages = await comment_pages_request.json()
                comment_pages = comment_pages["articleNames"]
            except aiohttp.ClientResponseError:  # Fandom can be funny sometimes... See #30
                comment_pages = None
            except:
                if command_line_args.debug:
                    logger.exception("Exception on Feeds article comment request")
                else:
                    logger.exception("Exception on Feeds article comment request")
                    # TODO
        message_list = defaultdict(list)
        for post in discussion_feed:  # Yeah, second loop since the comments require an extra request
            if post["id"] > wiki.discussion_id:
                for target in wiki.discussion_targets.items():
                    try:
                        message = await essential_feeds(post, comment_pages, wiki, target)
                        if message is not None:
                            message_list[target[0]].append(message)
                    except asyncio.CancelledError:
                        raise
                    except:
                        if command_line_args.debug:
                            logger.exception("Exception on Feeds formatter")
                            shutdown(loop=asyncio.get_event_loop())
                        else:
                            logger.exception("Exception on Feeds formatter")
                            await generic_msg_sender_exception_logger(traceback.format_exc(),
                                                                      "Exception in feed formatter",
                                                                      Post=str(post)[0:1000], Wiki=db_wiki["wiki"])
        # Lets stack the messages
        for messages in message_list.values():
            messages = stack_message_list(messages)
            for message in messages:
                await send_to_discord(message)
        if discussion_feed:
            DBHandler.add(db_wiki["wiki"], post["id"], True)
        await asyncio.sleep(delay=2.0)  # hardcoded really doesn't need much mor


async def essential_feeds(change: dict, comment_pages: dict, wiki: Wiki, target: tuple[Settings, list[str]]) -> DiscordMessage:
    """Prepares essential information for both embed and compact message format."""
    identification_string = change["_embedded"]["thread"][0]["containerType"]
    comment_page = None
    if identification_string == "ARTICLE_COMMENT" and comment_pages is not None:
        comment_page = comment_pages.get(change["forumId"], None)
        if comment_page is not None:
            comment_page["fullUrl"] = "/".join(wiki.script_url.split("/", 3)[:3]) + comment_page["relativeUrl"]
    metadata = DiscordMessageMetadata("POST", rev_id=None, log_id=None, page_id=None)
    context = Context("embed" if target[0].display > 0 else "compact", "recentchanges", target[1], wiki.client,
                      langs[target[0].lang]["rc_formatters"], prepare_settings(target[0].display))
    discord_message: Optional[DiscordMessage] = None
    try:
        discord_message = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(default_message(identification_string,context.message_type,formatter_hooks), context, change))
    except:
        if settings.get("error_tolerance", 1) > 0:
            logger.exception("Exception on discord message creation in essential_feeds")
        else:
            raise
    if discord_message:  # TODO How to react when none? (crash in formatter), probably bad handling atm
        discord_message.finish_embed()
        discord_message.metadata = metadata
    return discord_message
