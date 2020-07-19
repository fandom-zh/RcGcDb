from html.parser import HTMLParser
import base64, re
from src.config import settings
import json
import logging
from collections import defaultdict
import random
import math
profile_fields = {"profile-location": _("Location"), "profile-aboutme": _("About me"), "profile-link-google": _("Google link"), "profile-link-facebook":_("Facebook link"), "profile-link-twitter": _("Twitter link"), "profile-link-reddit": _("Reddit link"), "profile-link-twitch": _("Twitch link"), "profile-link-psn": _("PSN link"), "profile-link-vk": _("VK link"), "profile-link-xbl": _("XBL link"), "profile-link-steam": _("Steam link"), "profile-link-discord": _("Discord handle"), "profile-link-battlenet": _("Battle.net handle")}
logger = logging.getLogger("rcgcdw.misc")

class DiscordMessage():
	"""A class defining a typical Discord JSON representation of webhook payload."""
	def __init__(self, message_type: str, event_type: str, webhook_url: str, content=None):
		self.webhook_object = dict(allowed_mentions={"parse": []}, avatar_url=settings["avatars"].get(message_type, ""))
		self.webhook_url = webhook_url

		if message_type == "embed":
			self.__setup_embed()
		elif message_type == "compact":
			self.webhook_object["content"] = content

		self.event_type = event_type

	def __setitem__(self, key, value):
		"""Set item is used only in embeds."""
		try:
			self.embed[key] = value
		except NameError:
			raise TypeError("Tried to assign a value when message type is plain message!")

	def __getitem__(self, item):
		return self.embed[item]

	def __repr__(self):
		"""Return the Discord webhook object ready to be sent"""
		return json.dumps(self.webhook_object)

	def __setup_embed(self):
		self.embed = defaultdict(dict)
		if "embeds" not in self.webhook_object:
			self.webhook_object["embeds"] = [self.embed]
		else:
			self.webhook_object["embeds"].append(self.embed)
		self.embed["color"] = None

	def add_embed(self):
		self.finish_embed()
		self.__setup_embed()

	def finish_embed(self):
		if self.embed["color"] is None:
			if settings["appearance"]["embed"].get(self.event_type, {"color": None})["color"] is None:
				self.embed["color"] = random.randrange(1, 16777215)
			else:
				self.embed["color"] = settings["appearance"]["embed"][self.event_type]["color"]
		else:
			self.embed["color"] = math.floor(self.embed["color"])

	def set_author(self, name, url, icon_url=""):
		self.embed["author"]["name"] = name
		self.embed["author"]["url"] = url
		self.embed["author"]["icon_url"] = icon_url

	def add_field(self, name, value, inline=False):
		if "fields" not in self.embed:
			self.embed["fields"] = []
		self.embed["fields"].append(dict(name=name, value=value, inline=inline))

	def set_avatar(self, url):
		self.webhook_object["avatar_url"] = url

	def set_name(self, name):
		self.webhook_object["username"] = name


class LinkParser(HTMLParser):
	new_string = ""
	recent_href = ""

	def __init__(self, domain):
		super().__init__()
		self.WIKI_JUST_DOMAIN = domain

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


def link_formatter(link: str) -> str:
	"""Formats a link to not embed it"""
	return "<" + re.sub(r"([)])", "\\\\\\1", link).replace(" ", "_") + ">"


def escape_formatting(data: str) -> str:
	"""Escape Discord formatting"""
	return re.sub(r"([`_*~<>{}@/|\\])", "\\\\\\1", data, 0)


def create_article_path(article: str, WIKI_ARTICLE_PATH: str) -> str:
	"""Takes the string and creates an URL with it as the article name"""
	return WIKI_ARTICLE_PATH.replace("$1", article)


def profile_field_name(name, embed):
	try:
		return profile_fields[name]
	except KeyError:
		if embed:
			return _("Unknown")
		else:
			return _("unknown")


class ContentParser(HTMLParser):
	more = _("\n__And more__")
	current_tag = ""
	small_prev_ins = ""
	small_prev_del = ""
	ins_length = len(more)
	del_length = len(more)
	added = False

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


class RecentChangesClass():
	"""Store verious data and functions related to wiki and fetching of Recent Changes"""
	def __init__(self):
		self.tags = {}
		self.mw_messages = {}
		self.namespaces = None
		self.session = session

	@staticmethod
	def handle_mw_errors(request):
		if "errors" in request:
			logger.error(request["errors"])
			raise MWError
		return request

	def safe_request(self, url):
		try:
			request = self.session.get(url, timeout=10, allow_redirects=False)
		except requests.exceptions.Timeout:
			logger.warning("Reached timeout error for request on link {url}".format(url=url))
			self.downtime_controller()
			return None
		except requests.exceptions.ConnectionError:
			logger.warning("Reached connection error for request on link {url}".format(url=url))
			self.downtime_controller()
			return None
		except requests.exceptions.ChunkedEncodingError:
			logger.warning("Detected faulty response from the web server for request on link {url}".format(url=url))
			self.downtime_controller()
			return None
		else:
			if 499 < request.status_code < 600:
				self.downtime_controller()
				return None
			elif request.status_code == 302:
				logger.warning("Redirect detected! Either the wiki given in the script settings (wiki field) is incorrect/the wiki got removed or Gamepedia is giving us the false value. Please provide the real URL to the wiki, current URL redirects to {}".format(request.next.url))
			return request

	def init_info(self):
		return