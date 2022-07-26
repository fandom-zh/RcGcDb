from __future__ import annotations
import asyncio
import logging
from collections import OrderedDict
from src.config import settings
from typing import TYPE_CHECKING, Optional
from functools import cache
logger = logging.getLogger("rcgcdb.domain")

if TYPE_CHECKING:
    import src.wiki
    import src.wiki_ratelimiter
    import src.irc_feed


class Domain:
    def __init__(self, name: str):
        self.name = name  # This should be always in format of topname.extension for example fandom.com
        self.task: Optional[asyncio.Task] = None
        self.wikis: OrderedDict[str, src.wiki.Wiki] = OrderedDict()  # TODO Check if we can replace with https://docs.python.org/3/library/asyncio-queue.html
        self.rate_limiter: src.wiki_ratelimiter = src.wiki_ratelimiter.RateLimiter()
        self.irc: Optional[src.irc_feed.AioIRCCat] = None

    def __iter__(self):
        return iter(self.wikis)

    def __getitem__(self, item):
        return

    def __len__(self):
        return len(self.wikis)

    def get_wiki(self, item, default=None) -> Optional[src.wiki.Wiki]:
        return self.wikis.get(item, default)

    def set_irc(self, irc_client: src.irc_feed.AioIRCCat):
        self.irc = irc_client

    def stop_task(self):
        """Cancells the task"""
        self.task.cancel()  # Be aware that cancelling the task may take time

    def run_domain(self):
        if not self.task or self.task.cancelled():
            self.task = asyncio.create_task(self.run_wiki_check())
        else:
            logger.error(f"Tried to start a task for domain {self.name} however the task already exists!")

    def remove_wiki(self, script_url: str):
        self.wikis.pop(script_url)

    def add_wiki(self, wiki: src.wiki.Wiki, first=False):
        """Adds a wiki to domain list.

        :parameter wiki - Wiki object
        :parameter first (optional) - bool indicating if wikis should be added as first or last in the ordered dict"""
        wiki.set_domain(self)
        if wiki.script_url in self.wikis:
            self.wikis[wiki.script_url].update_targets()
        self.wikis[wiki.script_url] = wiki
        if first:
            self.wikis.move_to_end(wiki.script_url, last=False)

    async def run_wiki_scan(self, wiki: src.wiki.Wiki):
        await self.rate_limiter.timeout_wait()
        await wiki.scan()
        self.wikis.move_to_end(wiki.script_url)
        self.rate_limiter.timeout_add(1.0)

    async def irc_scheduler(self):
        while True:
            try:
                wiki_url = self.irc.updated_wikis.pop()
            except KeyError:
                break
            try:
                wiki = self.wikis[wiki_url]
            except KeyError:
                logger.error(f"Could not find a wiki with URL {wiki_url} in the domain group!")
                continue
            await self.run_wiki_scan(wiki)
        for wiki in self.wikis.values():
            if wiki.statistics.last_checked_rc < settings.get("irc_overtime", 3600):
                await self.run_wiki_scan(wiki)
            else:
                return  # Recently scanned wikis will get at the end of the self.wikis, so we assume what is first hasn't been checked for a while

    async def regular_scheduler(self):
        while True:
            await asyncio.sleep(self.calculate_sleep_time(len(self)))  # To make sure that we don't spam domains with one wiki every second we calculate a sane timeout for domains with few wikis
            await self.run_wiki_scan(next(iter(self.wikis.values())))

    @cache
    def calculate_sleep_time(self, queue_length: int):
        return max((-25 * queue_length) + 150, 1)

    async def run_wiki_check(self):
        if self.irc:
            while True:
                await self.irc_scheduler()
                await asyncio.sleep(10.0)
        else:
            await self.regular_scheduler()
