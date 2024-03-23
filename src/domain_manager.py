from __future__ import annotations
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse, urlunparse
import logging
import asyncpg
import asyncio
from src.exceptions import NoDomain
from src.config import settings
from src.domain import Domain
from src.irc_feed import AioIRCCat
from io import StringIO
from contextlib import redirect_stdout
from src.wiki import Wiki

logger = logging.getLogger("rcgcdb.domain_manager")


def safe_type_for_id(unsafe_id: str, target: Callable):
    if unsafe_id == "null" or unsafe_id == "":  # TODO Verify if correct
        return None
    return target(unsafe_id)


class DomainManager:
    def __init__(self):
        self.domains: dict[str, Domain] = {}

    async def webhook_update(self, connection: asyncpg.Connection, pid: int, channel: str, payload: str):
        """Callback for database listener. Used to update our domain cache on changes such as new wikis or removed wikis"""
        split_payload = payload.split(" ")
        logger.debug("Received pub/sub message: {}".format(payload))
        if len(split_payload) < 2:
            raise ValueError("Improper pub/sub message! Pub/sub payload: {}".format(payload))
        if split_payload[0] == "ADD":
            await self.new_wiki(Wiki(split_payload[1], safe_type_for_id(split_payload[2], int), safe_type_for_id(split_payload[3], str)))
        elif split_payload[0] == "REMOVE":
            try:
                results = await connection.fetch("SELECT * FROM rcgcdb WHERE wiki = $1;", split_payload[1])
                if len(results) > 0:  # If there are still webhooks for this wiki - just update its targets
                    await self.return_domain(self.get_domain(split_payload[1])).get_wiki(split_payload[1]).update_targets()
                else:
                    self.remove_wiki(split_payload[1])
            except asyncpg.IdleSessionTimeoutError:
                logger.error("Couldn't check amount of webhooks with {} wiki!".format(split_payload[1]))
                return
        elif split_payload[0] == "UPDATE":
            await self.return_domain(self.get_domain(split_payload[1])).get_wiki(split_payload[1]).update_targets()
            logger.info("Successfully force updated information about {}".format(split_payload[1]))
        elif split_payload[0] == "DEBUG":
            if split_payload[1] == "INFO":
                logger.info(self.domains)
                for name, domain in self.domains.items():
                    logger.info("RCGCDBDEBUG {name} - Status: {status}, exception: {exception}, irc: {irc}".format(name=name, status=domain.task.done(),
                                                                                           exception=domain.task.print_stack(), irc=str(domain.irc)))
                for item in asyncio.all_tasks():  # Get discussions task
                    if item.get_name() == "discussions":
                        logger.info(item)
                if self.check_for_domain(self.get_domain(split_payload[1])):
                    logger.info(str(self.return_domain(self.get_domain(split_payload[1])).get_wiki(split_payload[1])))
            elif split_payload[1] == "EXEC":
                f = StringIO()
                with redirect_stdout(f):
                    exec(" ".join(split_payload[2:]))
                logger.info(f.getvalue())
            elif split_payload[1] == "WIKI" and len(split_payload) > 2:
                domain = self.return_domain(self.get_domain(split_payload[2]))
                logger.info("RCGCDBDEBUG Domain information for {}: {}".format(domain.name, str(domain)))
                logger.info("RCGCDBDEBUG Wiki information for {}: {}".format(split_payload[2], domain.get_wiki(split_payload[2])))
        else:
            raise ValueError("Unknown pub/sub command! Payload: {}".format(payload))

    async def new_wiki(self, wiki: Wiki):
        """Finds a domain for the wiki and adds a wiki to the domain object.

        :parameter wiki - Wiki object to be added"""
        wiki_domain = self.get_domain(wiki.script_url)
        try:
            await self.domains[wiki_domain].add_wiki(wiki)
        except KeyError:
            new_domain = await self.new_domain(wiki_domain)
            await new_domain.add_wiki(wiki)

    def remove_domain(self, domain: Domain):
        logger.debug("Destroying domain and removing it from domain directory")
        domain.destroy()
        del self.domains[domain.name]

    def remove_wiki(self, script_url: str):
        wiki_domain = self.get_domain(script_url)
        try:
            domain = self.domains[wiki_domain]
        except KeyError:
            raise NoDomain
        else:
            domain.remove_wiki(script_url)
            logger.debug(f"Removed a wiki {script_url} from {domain.name}")
            if len(domain) == 0:
                self.remove_domain(domain)
                logger.debug(f"Removed domain {domain.name} due to removal of last queued wiki in its dictionary")

    @staticmethod
    def get_domain(url: str) -> str:
        """Returns a domain for given URL (for example fandom.com, wikipedia.org)"""
        parsed_url = urlparse(url)
        return ".".join(urlunparse((*parsed_url[0:2], "", "", "", "")).split(".")[-2:])

    def check_for_domain(self, domain: str):
        return domain in self.domains

    def return_domain(self, domain: str):
        return self.domains[domain]

    async def new_domain(self, name: str) -> Domain:
        logger.debug("Creating new domain object for {}".format(name))
        domain_object = Domain(name)
        for irc_server in settings["irc_servers"].keys():
            if name in settings["irc_servers"][irc_server]["domains"]:
                domain_object.set_irc(AioIRCCat(settings["irc_servers"][irc_server]["irc_channel_mapping"], domain_object, None, None))
                domain_object.irc.connect(settings["irc_servers"][irc_server]["irc_host"], settings["irc_servers"][irc_server]["irc_port"],
                                          settings["irc_servers"][irc_server]["irc_name"], ircname=settings["irc_servers"][irc_server]["irc_nickname"])
                break  # Allow only one IRC for a domain
        self.domains[name] = domain_object
        return self.domains[name]

    def run_all_domains(self):
        for domain in self.domains.values():
            domain.run_domain()


domains = DomainManager()
