from __future__ import annotations
import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    import src.wiki
    import src.wiki_ratelimiter
    import irc.client_aio


class Domain:
    def __init__(self, name: str):
        self.name = name  # This should be always in format of topname.extension for example fandom.com
        self.task: asyncio.Task = self.create_task()
        self.wikis: OrderedDict[str, src.wiki.Wiki] = OrderedDict()
        self.rate_limiter: src.wiki_ratelimiter = src.wiki_ratelimiter.RateLimiter()
        self.irc = None

    def __iter__(self):
        return iter(self.wikis)

    def __getitem__(self, item):
        return

    def set_irc(self, irc_client: irc.client_aio.AioSimpleIRCClient):
        self.irc = irc_client

    def add_wiki(self, wiki: src.wiki.Wiki, first=False):
        """Adds a wiki to domain list.

        :parameter wiki - Wiki object
        :parameter first (optional) - bool indicating if wikis should be added as first or last in the ordered dict"""
        self.wikis[wiki.script_url] = wiki
        if first:
            self.wikis.move_to_end(wiki.script_url, last=False)

    def create_task(self) -> asyncio.Task:
        return asyncio.create_task(self.run_wiki_check())

    async def run_wiki_check(self):
        raise NotImplementedError
