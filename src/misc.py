from html.parser import HTMLParser
import base64, re

import logging
from urllib.parse import urlparse, urlunparse
import aiohttp

logger = logging.getLogger("rcgcdw.misc")


def get_paths(wiki: str, request) -> tuple:
	parsed_url = urlparse(wiki)
	WIKI_API_PATH = wiki + request["query"]["general"]["scriptpath"] + "api.php"
	WIKI_SCRIPT_PATH = wiki
	WIKI_ARTICLE_PATH = urlunparse((*parsed_url[0:2], "", "", "", "")) + request["query"]["general"]["articlepath"]
	WIKI_JUST_DOMAIN = urlunparse((*parsed_url[0:2], "", "", "", ""))
	return WIKI_API_PATH, WIKI_SCRIPT_PATH, WIKI_ARTICLE_PATH, WIKI_JUST_DOMAIN


class LinkParser(HTMLParser):

	new_string = ""
	recent_href = ""
	WIKI_JUST_DOMAIN = ""

	def handle_starttag(self, tag, attrs):
		for attr in attrs:
			if attr[0] == 'href':
				self.recent_href = attr[1]
				if self.recent_href.startswith("//"):
					self.recent_href = "https:{rest}".format(rest=self.recent_href)
				elif not self.recent_href.startswith("http"):
					self.recent_href = self.WIKI_JUST_DOMAIN + self.recent_href
				self.recent_href = self.recent_href.replace(")", "\\)")
			elif attr[0] == 'data-uncrawlable-url':
				self.recent_href = attr[1].encode('ascii')
				self.recent_href = base64.b64decode(self.recent_href)
				self.recent_href = self.WIKI_JUST_DOMAIN + self.recent_href.decode('ascii')

	def handle_data(self, data):
		if self.recent_href:
			self.new_string = self.new_string + "[{}](<{}>)".format(data, self.recent_href)
			self.recent_href = ""
		else:
			self.new_string = self.new_string + data

	def handle_comment(self, data):
		self.new_string = self.new_string + data

	def handle_endtag(self, tag):
		# logger.debug(self.new_string)
		pass


LinkParse = LinkParser()

def parse_link(domain: str, to_parse: str) -> str:
	"""Because I have strange issues using the LinkParser class myself, this is a helper function
	to utilize the LinkParser properly"""
	LinkParse.WIKI_JUST_DOMAIN = domain
	LinkParse.feed(to_parse)
	LinkParse.new_string = ""
	LinkParse.recent_href = ""
	return LinkParse.new_string


def link_formatter(link: str) -> str:
	"""Formats a link to not embed it"""
	return "<" + re.sub(r"([)])", "\\\\\\1", link).replace(" ", "_") + ">"


def escape_formatting(data: str) -> str:
	"""Escape Discord formatting"""
	return re.sub(r"([`_*~<>{}@/|\\])", "\\\\\\1", data, 0)


def create_article_path(article: str, WIKI_ARTICLE_PATH: str) -> str:
	"""Takes the string and creates an URL with it as the article name"""
	return WIKI_ARTICLE_PATH.replace("$1", article)


def profile_field_name(name, embed, _):
	profile_fields = {"profile-location": _("Location"), "profile-aboutme": _("About me"),
	                  "profile-link-google": _("Google link"), "profile-link-facebook": _("Facebook link"),
	                  "profile-link-twitter": _("Twitter link"), "profile-link-reddit": _("Reddit link"),
	                  "profile-link-twitch": _("Twitch link"), "profile-link-psn": _("PSN link"),
	                  "profile-link-vk": _("VK link"), "profile-link-xbl": _("XBL link"),
	                  "profile-link-steam": _("Steam link"), "profile-link-discord": _("Discord handle"),
	                  "profile-link-battlenet": _("Battle.net handle")}

	try:
		return profile_fields[name]
	except KeyError:
		if embed:
			return _("Unknown")
		else:
			return _("unknown")


class ContentParser(HTMLParser):
	current_tag = ""
	small_prev_ins = ""
	small_prev_del = ""
	added = False

	def __init__(self, _):
		super().__init__()
		self.more = _("\n__And more__")
		self.ins_length = len(self.more)
		self.del_length = len(self.more)

	def handle_starttag(self, tagname, attribs):
		if tagname == "ins" or tagname == "del":
			self.current_tag = tagname
		if tagname == "td" and 'diff-addedline' in attribs[0]:
			self.current_tag = tagname + "a"
		if tagname == "td" and 'diff-deletedline' in attribs[0]:
			self.current_tag = tagname + "d"
		if tagname == "td" and 'diff-marker' in attribs[0]:
			self.added = True

	def handle_data(self, data):
		data = re.sub(r"([`_*~<>{}@/|\\])", "\\\\\\1", data, 0)
		if self.current_tag == "ins" and self.ins_length <= 1000:
			self.ins_length += len("**" + data + '**')
			if self.ins_length <= 1000:
				self.small_prev_ins = self.small_prev_ins + "**" + data + '**'
			else:
				self.small_prev_ins = self.small_prev_ins + self.more
		if self.current_tag == "del" and self.del_length <= 1000:
			self.del_length += len("~~" + data + '~~')
			if self.del_length <= 1000:
				self.small_prev_del = self.small_prev_del + "~~" + data + '~~'
			else:
				self.small_prev_del = self.small_prev_del + self.more
		if (self.current_tag == "afterins" or self.current_tag == "tda") and self.ins_length <= 1000:
			self.ins_length += len(data)
			if self.ins_length <= 1000:
				self.small_prev_ins = self.small_prev_ins + data
			else:
				self.small_prev_ins = self.small_prev_ins + self.more
		if (self.current_tag == "afterdel" or self.current_tag == "tdd") and self.del_length <= 1000:
			self.del_length += len(data)
			if self.del_length <= 1000:
				self.small_prev_del = self.small_prev_del + data
			else:
				self.small_prev_del = self.small_prev_del + self.more
		if self.added:
			if data == '+' and self.ins_length <= 1000:
				self.ins_length += 1
				if self.ins_length <= 1000:
					self.small_prev_ins = self.small_prev_ins + '\n'
				else:
					self.small_prev_ins = self.small_prev_ins + self.more
			if data == '−' and self.del_length <= 1000:
				self.del_length += 1
				if self.del_length <= 1000:
					self.small_prev_del = self.small_prev_del + '\n'
				else:
					self.small_prev_del = self.small_prev_del + self.more
			self.added = False

	def handle_endtag(self, tagname):
		if tagname == "ins":
			self.current_tag = "afterins"
		elif tagname == "del":
			self.current_tag = "afterdel"
		else:
			self.current_tag = ""


async def safe_read(request: aiohttp.ClientResponse, *keys):
	if request is None:
		return None
	try:
		request = await request.json(encoding="UTF-8")
		for item in keys:
			request = request[item]
	except KeyError:
		logger.warning(
			"Failure while extracting data from request on key {key} in {change}".format(key=item, change=request))
		return None
	except aiohttp.ClientResponseError:
		logger.warning("Failure while extracting data from request in {change}".format(change=request))
		return None
	return request
