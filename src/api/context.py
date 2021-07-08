#  This file is part of Recent changes Goat compatible Discord bot (RcGcDb).
#
#  RcGcDb is free software: you can redistribute it and/or modify
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
#  along with RcGcDb.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from src.api.client import Client


class Context:
	"""Context object containing client and some metadata regarding specific formatter call"""
	def __init__(self, message_type: str, webhook_url: str, client: Client):
		self.client = client
		self.webhook_url = webhook_url
		self.message_type = message_type
		self.categories = None
		self.parsedcomment = None
		self.event = None
		self.comment_page = None

	def set_categories(self, cats):
		self.categories = cats

	def set_parsedcomment(self, parsedcomment: str):
		self.parsedcomment = parsedcomment

	def set_comment_page(self, page):
		self.comment_page = page
