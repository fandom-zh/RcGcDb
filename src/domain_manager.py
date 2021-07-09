from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse, urlunparse
from src.config import settings
from src.domain import Domain
from src.irc_feed import AioIRCCat


if TYPE_CHECKING:
    from src.wiki import Wiki


class DomainManager:
    def __init__(self):
        self.domains: dict[str, Domain] = {}

    async def new_wiki(self, wiki: Wiki):
        """Finds a domain for the wiki and adds a wiki to the domain object.

        :parameter wiki - Wiki object to be added"""
        wiki_domain = self.get_domain(wiki.script_url)
        try:
            self.domains[wiki_domain].add_wiki(wiki)
        except KeyError:
            new_domain = await self.new_domain(wiki_domain)
            new_domain.add_wiki(wiki)

    def remove_wiki(self, script_url: str):
        wiki_domain = self.get_domain(script_url)
        try:
            domain = self.domains[wiki_domain]
        except KeyError:
            raise NoDomain
        else:
            domain.remove_wiki(script_url)

    @staticmethod
    def get_domain(url: str) -> str:
        """Returns a domain for given URL (for example fandom.com, wikipedia.org)"""
        parsed_url = urlparse(url)
        return ".".join(urlunparse((*parsed_url[0:2], "", "", "", "")).split(".")[-2:])

    async def new_domain(self, name: str) -> Domain:
        domain_object = Domain(name)
        for irc_server in settings["irc_servers"].keys():
            if name in settings["irc_servers"][irc_server]["domains"]:
                domain_object.set_irc(AioIRCCat(settings["irc_servers"][irc_server]["irc_channel_mapping"], domain_object))
                break  # Allow only one IRC for a domain
        self.domains[name] = domain_object
        return self.domains[name]

    async def run_all_domains(self):
        for domain in self.domains.values():
            domain.run_domain()

domains = DomainManager()
