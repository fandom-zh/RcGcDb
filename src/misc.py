from html.parser import HTMLParser
import base64, re

import logging
from urllib.parse import urlparse, urlunparse
from src.i18n import langs

logger = logging.getLogger("rcgcdw.misc")


def get_paths(wiki: str, request) -> tuple:
	"""Prepares wiki paths for the functions"""
	parsed_url = urlparse(wiki)
	WIKI_API_PATH = wiki + "api.php"
	WIKI_SCRIPT_PATH = wiki
	WIKI_ARTICLE_PATH = urlunparse((*parsed_url[0:2], "", "", "", "")) + request["query"]["general"]["articlepath"]
	WIKI_JUST_DOMAIN = urlunparse((*parsed_url[0:2], "", "", "", ""))
	return WIKI_API_PATH, WIKI_SCRIPT_PATH, WIKI_ARTICLE_PATH, WIKI_JUST_DOMAIN


def get_domain(url: str) -> str:
	"""Get domain of given URL"""
	parsed_url = urlparse(url)
	return ".".join(urlunparse((*parsed_url[0:2], "", "", "", "")).split(".")[-2:])  # something like gamepedia.com, fandom.com


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
			self.new_string = self.new_string + "[{}](<{}>)".format(escape_formatting(data), self.recent_href)
			self.recent_href = ""
		else:
			self.new_string = self.new_string + escape_formatting(data)

	def handle_comment(self, data):
		self.new_string = self.new_string + escape_formatting(data)

	def handle_endtag(self, tag):
		# logger.debug(self.new_string)
		pass


LinkParse = LinkParser()

def parse_link(domain: str, to_parse: str) -> str:
	"""Because I have strange issues using the LinkParser class myself, this is a helper function
	to utilize the LinkParser properly"""
	LinkParse.WIKI_JUST_DOMAIN = domain
	LinkParse.new_string = ""
	LinkParse.feed(to_parse)
	LinkParse.recent_href = ""
	return LinkParse.new_string


def link_formatter(link: str) -> str:
	"""Formats a link to not embed it"""
	return "<" + re.sub(r"([)])", "\\\\\\1", link).replace(" ", "_") + ">"


def escape_formatting(data: str) -> str:
	"""Escape Discord formatting"""
	return re.sub(r"([`_*~:<>{}@/|\\\[\]\(\)])", "\\\\\\1", data, 0) if data is not None else ""


def create_article_path(article: str, WIKI_ARTICLE_PATH: str) -> str:
	"""Takes the string and creates an URL with it as the article name"""
	article = article.replace(" ", "_").replace("%", "%25").replace("\\", "%5C")
	if "?" in WIKI_ARTICLE_PATH:
		article = article.replace("&", "%26")
	else:
		article = article.replace("?", "%3F")
	return WIKI_ARTICLE_PATH.replace("$1", article)


def profile_field_name(name, embed, lang):
	_ = langs[lang]["misc"].gettext
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
	last_ins = None
	last_del = None
	empty = False
	small_prev_ins = ""
	small_prev_del = ""

	def __init__(self, lang):
		super().__init__()
		self.more = langs[lang]["misc"].gettext("\n__And more__")
		self.ins_length = len(self.more)
		self.del_length = len(self.more)

	def handle_starttag(self, tagname, attribs):
		if tagname == "ins" or tagname == "del":
			self.current_tag = tagname
		if tagname == "td" and "diff-addedline" in attribs[0] and self.ins_length <= 1000:
			self.current_tag = "tda"
			self.last_ins = ""
		if tagname == "td" and "diff-deletedline" in attribs[0] and self.del_length <= 1000:
			self.current_tag = "tdd"
			self.last_del = ""
		if tagname == "td" and "diff-empty" in attribs[0]:
			self.empty = True

	def handle_data(self, data):
		data = escape_formatting(data)
		if self.current_tag == "ins" and self.ins_length <= 1000:
			self.ins_length += len("**" + data + "**")
			if self.ins_length <= 1000:
				self.last_ins = self.last_ins + "**" + data + "**"
		if self.current_tag == "del" and self.del_length <= 1000:
			self.del_length += len("~~" + data + "~~")
			if self.del_length <= 1000:
				self.last_del = self.last_del + "~~" + data + "~~"
		if self.current_tag == "tda" and self.ins_length <= 1000:
			self.ins_length += len(data)
			if self.ins_length <= 1000:
				self.last_ins = self.last_ins + data
		if self.current_tag == "tdd" and self.del_length <= 1000:
			self.del_length += len(data)
			if self.del_length <= 1000:
				self.last_del = self.last_del + data

	def handle_endtag(self, tagname):
		self.current_tag = ""
		if tagname == "ins":
			self.current_tag = "tda"
		elif tagname == "del":
			self.current_tag = "tdd"
		elif tagname == "tr":
			if self.last_ins is not None:
				self.ins_length += 1
				if self.empty and not self.last_ins.isspace() and "**" not in self.last_ins:
					self.ins_length += 4
					self.last_ins = "**" + self.last_ins + "**"
				self.small_prev_ins = self.small_prev_ins + "\n" + self.last_ins
				if self.ins_length > 1000:
					self.small_prev_ins = self.small_prev_ins + self.more
				self.last_ins = None
			if self.last_del is not None:
				self.del_length += 1
				if self.empty and not self.last_del.isspace() and "~~" not in self.last_del:
					self.del_length += 4
					self.last_del = "~~" + self.last_del + "~~"
				self.small_prev_del = self.small_prev_del + "\n" + self.last_del
				if self.del_length > 1000:
					self.small_prev_del = self.small_prev_del + self.more
				self.last_del = None
			self.empty = False
