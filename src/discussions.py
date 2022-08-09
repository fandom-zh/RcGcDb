from collections import OrderedDict

import src.wiki


class Discussions():
    def __init__(self, wikis: OrderedDict[str, src.wiki.Wiki]):
        self.wikis = wikis

    async def tick_discussions(self):
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
            await self.run_discussion_scan(wiki)
        for wiki in self.wikis.values():
            if wiki.statistics.last_checked_discussion < settings.get("irc_overtime", 3600):
                await self.run_discussion_scan(wiki)
            else:
                return  # Recently scanned wikis will get at the end of the self.wikis, so we assume what is first hasn't been checked for a while

    async def add_wiki(self, wiki):