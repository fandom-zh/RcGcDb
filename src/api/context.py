#  This file is part of Recent changes Goat compatible Discord webhook (RcGcDw).
#
#  RcGcDw is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  RcGcDw is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with RcGcDw.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import annotations

import gettext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from src.api.client import Client


class Context:
	"""Context object containing client and some metadata regarding specific formatter call,
	they are mainly used as a bridge between part that fetches the changes and API's formatters"""
	def __init__(self, message_type: str, feed_type: str, webhook_urls: list[str], client: Client, language: gettext.GNUTranslations, settings: dict):
		self.client = client
		self.webhook_urls = webhook_urls
		self.message_type = message_type
		self.feed_type = feed_type
		self.categories = None
		self.parsedcomment = None
		self.event = None
		self.comment_page = None
		self._ = language.gettext  # Singular translations (ex. ctx._("Large goat"))
		self.gettext = language.gettext  # In case you dislike _ or using "protected field" of ctx
		self.ngettext = language.npgettext  # Plural translations depending on amount (ex. ctx.ngettext("{} action", "{} actions", action_amount))
		self.pgettext = language.pgettext  # Translation with context (ex. ctx.pgettext("From mediawiki module", "Blocked {} user"))
		self.npgettext = language.npgettext  # Plural translation with context (ex. ctx.npgettext("From mediawiki module", "Edited {} time", "Edited {} times", edit_amoint)
		self.settings = settings

	def set_categories(self, cats):
		self.categories = cats

	def set_parsedcomment(self, parsedcomment: str):
		self.parsedcomment = parsedcomment

	def set_comment_page(self, page):
		self.comment_page = page

	def __str__(self):
		return f"<Context message_type={self.message_type} feed_type={self.feed_type} event={self.event} webhook_urls={self.webhook_urls}"
