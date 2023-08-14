from __future__ import annotations
import asyncio
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional
from functools import cache

import aiohttp

from src.discord.message import DiscordMessage
from src.config import settings
from src.argparser import command_line_args
# from src.discussions import Discussions
from src.statistics import Log, LogType

logger = logging.getLogger("rcgcdb.domain")

if TYPE_CHECKING:
    import src.wiki
    import src.irc_feed


class Domain:
    def __init__(self, name: str):
        self.name = name  # This should be always in format of topname.extension for example fandom.com
        self.task: Optional[asyncio.Task] = None
        self.wikis: OrderedDict[str, src.wiki.Wiki] = OrderedDict()
        self.irc: Optional[src.irc_feed.AioIRCCat] = None
        self.failures = 0
        # self.discussions_handler: Optional[Discussions] = Discussions(self.wikis) if name == "fandom.com" else None

    def __iter__(self):
        return iter(self.wikis)

    def __str__(self) -> str:
        return f"<Domain name='{self.name}' task='{self.task}' wikis='{self.wikis}' irc='{self.irc.connection.connected}' failures={self.failures}>"

    def __repr__(self):
        return self.__str__()

    def __getitem__(self, item):
        return

    def __len__(self):
        return len(self.wikis)

    def destroy(self):
        """Destroy the domain – do all of the tasks that should make sure there is no leftovers before being collected by GC"""
        if self.irc:
            logger.debug("Leaving IRC due to destroy() for domain {}".format(self.name))
            self.irc.connection.die("Leaving")
        # if self.discussions_handler:
        #     self.discussions_handler.close()
        if self.task:
            self.task.cancel()

    def get_wiki(self, item, default=None) -> Optional[src.wiki.Wiki]:
        """Return a wiki with given domain name"""
        return self.wikis.get(item, default)

    def set_irc(self, irc_client: src.irc_feed.AioIRCCat):
        """Sets IRC"""
        self.irc = irc_client

    def stop_task(self):
        """Cancells the task"""
        self.task.cancel()  # Be aware that cancelling the task may take time

    def run_domain(self):
        """Starts asyncio task for domain"""
        if not self.task or self.task.cancelled():
            self.task = asyncio.create_task(self.run_wiki_check(), name=self.name)
        else:
            logger.error(f"Tried to start a task for domain {self.name} however the task already exists!")

    def remove_wiki(self, script_url: str):
        self.wikis.pop(script_url)

    async def add_wiki(self, wiki: src.wiki.Wiki, first=False):
        """Adds a wiki to domain list.

        :parameter wiki - Wiki object
        :parameter first (optional) - bool indicating if wikis should be added as first or last in the ordered dict"""
        wiki.set_domain(self)
        if wiki.script_url in self.wikis:
            await self.wikis[wiki.script_url].update_targets()
        else:
            self.wikis[wiki.script_url] = wiki
            await wiki.update_targets()
        if first:
            self.wikis.move_to_end(wiki.script_url, last=False)

    async def run_wiki_scan(self, wiki: src.wiki.Wiki, reason: Optional[int] = None):
        await wiki.scan()
        wiki.statistics.update(Log(type=LogType.SCAN_REASON, title=str(reason)))
        self.wikis.move_to_end(wiki.script_url)

    async def irc_scheduler(self):
        try:
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
            while True:  # Iterate until hitting return, we don't have to iterate using for since we are sending wiki to the end anyways
                wiki: src.wiki.Wiki = next(iter(self.wikis.values()))
                if (int(time.time()) - (wiki.statistics.last_checked_rc or 0)) > settings.get("irc_overtime", 3600):
                    await self.run_wiki_scan(wiki)
                else:
                    return  # Recently scanned wikis will get at the end of the self.wikis, so we assume what is first hasn't been checked for a while
        except Exception as e:
            if command_line_args.debug:
                logger.exception("IRC scheduler task for domain {} failed!".format(self.name))
            else:
                await self.send_exception_to_monitoring(e)
                self.failures += 1
                if self.failures > 2:
                    raise asyncio.exceptions.CancelledError

    async def regular_scheduler(self):
        try:
            while True:
                await asyncio.sleep(self.calculate_sleep_time(len(self)))  # To make sure that we don't spam domains with one wiki every second we calculate a sane timeout for domains with few wikis
                await self.run_wiki_scan(next(iter(self.wikis.values())))
        except Exception as e:
            if command_line_args.debug:
                logger.exception("IRC task for domain {} failed!".format(self.name))
            else:
                await self.send_exception_to_monitoring(e)
                self.failures += 1
                if self.failures > 2:
                    raise asyncio.exceptions.CancelledError

    @cache
    def calculate_sleep_time(self, queue_length: int):
        return max((-25 * queue_length) + 150, 1)

    async def run_wiki_check(self):
        """Runs appropriate scheduler depending on existence of IRC"""
        if self.irc:
            try:
                while True:
                    await self.irc_scheduler()
                    await asyncio.sleep(10.0)
            except asyncio.exceptions.CancelledError:
                for wiki in self.wikis.values():
                    await wiki.session.close()
                    self.irc.connection.disconnect()
        else:
            try:
                await self.regular_scheduler()
            except asyncio.exceptions.CancelledError:
                for wiki in self.wikis.values():
                    await wiki.session.close()

    async def send_exception_to_monitoring(self, ex: Exception):
        discord_message = DiscordMessage("embed", "generic", [""])
        discord_message["title"] = "Domain scheduler exception for {} (recovered)".format(self.name)
        discord_message["content"] = str(ex)[0:1995]
        discord_message.add_field("Failure count", self.failures)
        discord_message.finish_embed_message()
        header = settings["header"]
        header['Content-Type'] = 'application/json'
        header['X-RateLimit-Precision'] = "millisecond"
        try:
            async with aiohttp.ClientSession(headers=header, timeout=aiohttp.ClientTimeout(total=6)) as session:
                async with session.post("https://discord.com/api/webhooks/{}".format(settings["monitoring_webhook"]),
                                        data=repr(discord_message)) as resp:
                    pass
        except (aiohttp.ServerConnectionError, aiohttp.ServerTimeoutError):
            logger.exception("Couldn't communicate with Discord as a result of Server Error when trying to signal domain task issue!")