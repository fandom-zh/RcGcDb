from __future__ import annotations
import asyncio
import irc.client_aio
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    import src.wiki
    import src.wiki_ratelimiter


class Domain:
    def __init__(self, name: str, irc_client: Optional[irc.client_aio.AioSimpleIRCClient] = None):
        self.name = name  # This should be always in format of topname.extension for example fandom.com
        self.task: asyncio.Task = self.create_task()
        self.wikis: list[src.wiki.Wiki] = list()
        self.rate_limiter: src.wiki_ratelimiter = src.wiki_ratelimiter.RateLimiter()
        self.irc = irc_client

    def add_wiki(self, wiki: src.wiki.Wiki, index: int = None):
        """Adds a wiki to domain list.

        :parameter wiki - Wiki object
        :parameter index (optional) - index at which the wiki should be added, if not specified it's the end of the list"""
        if index:
            self.wikis.insert(index, wiki)
        else:
            self.wikis.append(wiki)

    def create_task(self) -> asyncio.Task:
        return asyncio.create_task(self.run_wiki_check())

    async def run_wiki_check(self):
        raise NotImplementedError
