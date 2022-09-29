from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse, urlunparse
import logging
import asyncpg

from src.exceptions import NoDomain
from src.config import settings
from src.domain import Domain
from src.irc_feed import AioIRCCat


if TYPE_CHECKING:
    from src.wiki import Wiki

logger = logging.getLogger("rcgcdb.domain_manager")

class DomainManager:
    def __init__(self):
        self.domains: dict[str, Domain] = {}

    async def webhook_update(self, connection: asyncpg.Connection, pid: int, channel: str, payload: str):
        """Callback for database listener. Used to update our domain cache on changes such as new wikis or removed wikis"""
        # TODO Write a trigger for pub/sub in database/Wiki-Bot repo
        split_payload = payload.split(" ")
        if len(split_payload) < 2:
            raise ValueError("Improper pub/sub message! Pub/sub payload: {}".format(payload))
        if split_payload[0] == "ADD":
            await self.new_wiki(Wiki(split_payload[1], None, None))
        elif split_payload[0] == "REMOVE":
            try:
                results = await connection.fetch("SELECT * FROM rcgcdw WHERE wiki = $1;", split_payload[1])
                if len(results) > 0:
                    return
            except asyncpg.IdleSessionTimeoutError:
                logger.error("Couldn't check amount of webhooks with {} wiki!".format(split_payload[1]))
                return
            self.remove_wiki(split_payload[1])
        else:
            raise ValueError("Unknown pub/sub command! Payload: {}".format(payload))

    async def new_wiki(self, wiki: Wiki):
        """Finds a domain for the wiki and adds a wiki to the domain object.

        :parameter wiki - Wiki object to be added"""
        wiki_domain = self.get_domain(wiki.script_url)
        try:
            self.domains[wiki_domain].add_wiki(wiki)
        except KeyError:
            new_domain = await self.new_domain(wiki_domain)
            new_domain.add_wiki(wiki)

    def remove_domain(self, domain):
        domain.destoy()
        del self.domains[domain]

    def remove_wiki(self, script_url: str):
        wiki_domain = self.get_domain(script_url)
        try:
            domain = self.domains[wiki_domain]
        except KeyError:
            raise NoDomain
        else:
            domain.remove_wiki(script_url)
            if len(domain) == 0:
                self.remove_domain(domain)

    @staticmethod
    def get_domain(url: str) -> str:
        """Returns a domain for given URL (for example fandom.com, wikipedia.org)"""
        parsed_url = urlparse(url)
        return ".".join(urlunparse((*parsed_url[0:2], "", "", "", "")).split(".")[-2:])

    def return_domain(self, domain: str):
        return self.domains[domain]

    async def new_domain(self, name: str) -> Domain:
        domain_object = Domain(name)
        for irc_server in settings["irc_servers"].keys():
            if name in settings["irc_servers"][irc_server]["domains"]:
                domain_object.set_irc(AioIRCCat(settings["irc_servers"][irc_server]["irc_channel_mapping"], domain_object))
                break  # Allow only one IRC for a domain
        self.domains[name] = domain_object
        return self.domains[name]

    def run_all_domains(self):
        for domain in self.domains.values():
            domain.run_domain()


domains = DomainManager()
