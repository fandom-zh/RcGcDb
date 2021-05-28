from __future__ import annotations
import asyncio
import irc.client_aio
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    import src.wiki
    import src.wiki_ratelimiter


class Domain:
    def __init__(self, task: asyncio.Task, irc_client: Optional[irc.client_aio.AioSimpleIRCClient] = None):
        self.task = task
        self.wikis: list[src.wiki.Wiki] = list()
        self.rate_limiter: src.wiki_ratelimiter = src.wiki_ratelimiter.RateLimiter()
        self.irc = irc_client

