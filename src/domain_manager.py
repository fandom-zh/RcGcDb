from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse, urlunparse
from src.config import settings
from src.domain import Domain


if TYPE_CHECKING:
    from src.wiki import Wiki


class DomainManager:
    def __init__(self):
        self.domains: dict[str, Domain] = {}

    def new_wiki(self, wiki: Wiki):
        """Finds a domain for the wiki and adds a wiki to the domain object.

        :parameter wiki - Wiki object to be added"""
        wiki_domain = self.get_domain(wiki.script_url)
        try:
            self.domains[wiki_domain].add_wiki(wiki)
        except KeyError:
            self.new_domain(wiki_domain).add_wiki(wiki)

    @staticmethod
    def get_domain(url: str) -> str:
        """Returns a domain for given URL (for example fandom.com, wikipedia.org)"""
        parsed_url = urlparse(url)
        return ".".join(urlunparse((*parsed_url[0:2], "", "", "", "")).split(".")[-2:])

    def new_domain(self, name: str) -> Domain:
        # TODO IRC Part
        self.domains[name] = Domain(name, irc)
        return self.domains[name]


domains = DomainManager()
