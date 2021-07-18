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
import src.misc
from src.exceptions import TagNotFound
from bs4 import BeautifulSoup
from typing import Union, TYPE_CHECKING, Optional
from collections import OrderedDict
from functools import cache
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
	from src.wiki import Wiki

class Client:
	"""
		A client for interacting with RcGcDw when creating formatters or hooks.
	"""
	def __init__(self, wiki):
		self.__recent_changes: Wiki = wiki
		self.content_parser = src.misc.ContentParser
		self.LinkParser: type(src.misc.LinkParser) = src.misc.LinkParser
		self.last_request: Optional[dict] = None
		#self.make_api_request: src.rc.wiki.__recent_changes.api_request = self.__recent_changes.api_request

	@property
	def namespaces(self) -> dict:
		"""Return a dict of namespaces, if None return empty dict"""
		if self.__recent_changes.namespaces is not None:
			return self.__recent_changes.namespaces
		else:
			return dict()

	@cache
	def tag(self, tag_name: str):
		for tag in self.last_request["tags"]:
			if tag["name"] == tag_name:
				try:
					return (BeautifulSoup(tag["displayname"], "lxml")).get_text()
				except KeyError:
					return None  # Tags with no display name are hidden and should not appear on RC as well
		raise TagNotFound

	@property
	def WIKI_API_PATH(self):
		return self.__recent_changes.script_url + "api.php"

	@property
	def WIKI_SCRIPT_PATH(self):
		return self.__recent_changes.script_url

	@property
	def WIKI_JUST_DOMAIN(self):
		parsed_url = urlparse(self.__recent_changes.script_url)
		return urlunparse((*parsed_url[0:2], "", "", "", ""))

	@property
	def WIKI_ARTICLE_PATH(self):
		parsed_url = urlparse(self.__recent_changes.script_url)
		try:
			return urlunparse((*parsed_url[0:2], "", "", "", "")) + self.last_request["query"]["general"]["articlepath"]
		except KeyError:
			return urlunparse((*parsed_url[0:2], "", "", "", "")) + "wiki/"

	def parse_links(self, summary: str):
		link_parser = self.LinkParser()
		link_parser.feed(summary)
		return link_parser.new_string

	def pull_curseprofile_comment(self, comment_id) -> Optional[str]:
		"""Pulls a CurseProfile comment for current wiki set in the settings and with comment_id passed as an argument.

		Returns:
			String if comment was possible to be fetched
			None if not
		"""
		return self.__recent_changes.pull_comment(comment_id)

	def make_api_request(self, params: Union[str, OrderedDict], *json_path: str, timeout: int = 10, allow_redirects: bool = False):
		"""Method to GET request data from the wiki's API with error handling including recognition of MediaWiki errors.

				Parameters:

					params (str, OrderedDict): a string or collections.OrderedDict object containing query parameters
					json_path (str): *args taking strings as values. After request is parsed as json it will extract data from given json path
					timeout (int, float) (default=10): int or float limiting time required for receiving a full response from a server before returning TimeoutError
					allow_redirects (bool) (default=False): switches whether the request should follow redirects or not

				Returns:

					request_content (dict): a dict resulting from json extraction of HTTP GET request with given json_path
					OR
					One of the following exceptions:
					ServerError: When connection with the wiki failed due to server error
					ClientError: When connection with the wiki failed due to client error
					KeyError: When json_path contained keys that weren't found in response JSON response
					BadRequest: When params argument is of wrong type
					MediaWikiError: When MediaWiki returns an error
				"""
		return self.__recent_changes.api_request(params, *json_path, timeout=timeout, allow_redirects=allow_redirects)

	def get_ipmapper(self) -> dict:
		"""Returns a dict mapping IPs with amount of their edits"""
		return self.__recent_changes.map_ips
