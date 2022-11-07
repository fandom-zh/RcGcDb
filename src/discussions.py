from __future__ import annotations

import asyncio
import logging
import typing
from collections import OrderedDict
from src.config import settings
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.domain import Domain
    from src.wiki import Wiki

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
            if wiki.statistics.last_checked_discussion < settings.get("irc_overtime", 3600):
                await self.run_discussion_scan(wiki)
            else:
                return  # Recently scanned wikis will get at the end of the self.wikis, so we assume what is first hasn't been checked for a while

    def filter_and_sort(self) -> list[Wiki]:
        """Filters and sorts wikis from domain to return only the ones that aren't -1 and sorts them from oldest in checking to newest"""
        # return OrderedDict(sorted(filter(lambda wiki: wiki[1].discussion_id != -1, self.domain_object.wikis.items()), key=lambda wiki: wiki[1].statistics.last_checked_discussion))
        return sorted(filter(lambda wiki: wiki.discussion_id != -1, self.domain_object.wikis.values()), key=lambda wiki: wiki.statistics.last_checked_discussion)

    async def run_discussion_scan(self, wiki: Wiki):
