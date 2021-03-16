import ipaddress
import math
import re
import time
import json
import logging
import datetime
from aiohttp import ClientResponseError
from src.config import settings
from src.misc import link_formatter, create_article_path, parse_link, profile_field_name, ContentParser
from src.discord import DiscordMessage
from src.i18n import langs

from bs4 import BeautifulSoup

logger = logging.getLogger("rcgcdw.rc_formatters")

if 1 == 2: # additional translation strings in unreachable code
	print(_("director"), _("bot"), _("editor"), _("directors"), _("sysop"), _("bureaucrat"), _("reviewer"),
	      _("autoreview"), _("autopatrol"), _("wiki_guardian"), ngettext("second", "seconds", 1), ngettext("minute", "minutes", 1), ngettext("hour", "hours", 1), ngettext("day", "days", 1), ngettext("week", "weeks", 1), ngettext("month", "months",1), ngettext("year", "years", 1), ngettext("millennium", "millennia", 1), ngettext("decade", "decades", 1), ngettext("century", "centuries", 1))

async def compact_formatter(action, change, parsed_comment, categories, recent_changes, message_target, paths, rate_limiter,
                            additional_data=None) -> DiscordMessage:
	"""Recent Changes compact formatter, part of RcGcDw"""
	_ = langs[message_target[0][0]]["rc_formatters"].gettext
	ngettext = langs[message_target[0][0]]["rc_formatters"].ngettext
	if additional_data is None:
		additional_data = {"namespaces": {}, "tags": {}}
	WIKI_API_PATH = paths[0]
	WIKI_SCRIPT_PATH = paths[1]
	WIKI_ARTICLE_PATH = paths[2]
	WIKI_JUST_DOMAIN = paths[3]
	if action != "suppressed":
		if "anon" in change:
			author_url = link_formatter(create_article_path("Special:Contributions/{user}".format(user=change["user"]), WIKI_ARTICLE_PATH))
		else:
			author_url = link_formatter(create_article_path("User:{user}".format(user=change["user"]), WIKI_ARTICLE_PATH))
		author = change["user"]
	parsed_comment = "" if parsed_comment is None else " *("+parsed_comment+")*"
	if action in ["edit", "new"]:
		edit_link = link_formatter("{wiki}index.php?title={article}&curid={pageid}&diff={diff}&oldid={oldrev}".format(
			wiki=WIKI_SCRIPT_PATH, pageid=change["pageid"], diff=change["revid"], oldrev=change["old_revid"],
			article=change["title"]))
		edit_size = change["newlen"] - change["oldlen"]
		sign = ""
		if edit_size > 0:
			sign = "+"
		bold = ""
		if abs(edit_size) > 500:
			bold = "**"
		if action == "edit":
			content = _("[{author}]({author_url}) edited [{article}]({edit_link}){comment} {bold}({sign}{edit_size}){bold}").format(author=author, author_url=author_url, article=change["title"], edit_link=edit_link, comment=parsed_comment, edit_size=edit_size, sign=sign, bold=bold)
		else:
			content = _("[{author}]({author_url}) created [{article}]({edit_link}){comment} {bold}({sign}{edit_size}){bold}").format(author=author, author_url=author_url, article=change["title"], edit_link=edit_link, comment=parsed_comment, edit_size=edit_size, sign=sign, bold=bold)
	elif action =="upload/upload":
		file_link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) uploaded [{file}]({file_link}){comment}").format(author=author,
		                                                                                    author_url=author_url,
		                                                                                    file=change["title"],
		                                                                                    file_link=file_link,
		                                                                                    comment=parsed_comment)
	elif action == "upload/revert":
		file_link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) reverted a version of [{file}]({file_link}){comment}").format(
			author=author, author_url=author_url, file=change["title"], file_link=file_link, comment=parsed_comment)
	elif action == "upload/overwrite":
		file_link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) uploaded a new version of [{file}]({file_link}){comment}").format(author=author, author_url=author_url, file=change["title"], file_link=file_link, comment=parsed_comment)
	elif action == "delete/delete":
		page_link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deleted [{page}]({page_link}){comment}").format(author=author, author_url=author_url, page=change["title"], page_link=page_link,
		                                                  comment=parsed_comment)
	elif action == "delete/delete_redir":
		page_link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deleted redirect by overwriting [{page}]({page_link}){comment}").format(author=author, author_url=author_url, page=change["title"], page_link=page_link,
		                                                   comment=parsed_comment)
	elif action == "move/move":
		link = link_formatter(create_article_path(change["logparams"]['target_title'], WIKI_ARTICLE_PATH))
		redirect_status = _("without making a redirect") if "suppressredirect" in change["logparams"] else _("with a redirect")
		content = _("[{author}]({author_url}) moved {redirect}*{article}* to [{target}]({target_url}) {made_a_redirect}{comment}").format(author=author, author_url=author_url, redirect="⤷ " if "redirect" in change else "", article=change["title"],
			target=change["logparams"]['target_title'], target_url=link, comment=parsed_comment, made_a_redirect=redirect_status)
	elif action == "move/move_redir":
		link = link_formatter(create_article_path(change["logparams"]["target_title"], WIKI_ARTICLE_PATH))
		redirect_status = _("without making a redirect") if "suppressredirect" in change["logparams"] else _(
			"with a redirect")
		content = _("[{author}]({author_url}) moved {redirect}*{article}* over redirect to [{target}]({target_url}) {made_a_redirect}{comment}").format(author=author, author_url=author_url, redirect="⤷ " if "redirect" in change else "", article=change["title"],
			target=change["logparams"]['target_title'], target_url=link, comment=parsed_comment, made_a_redirect=redirect_status)
	elif action == "protect/move_prot":
		link = link_formatter(create_article_path(change["logparams"]["oldtitle_title"], WIKI_ARTICLE_PATH))
		content = _(
			"[{author}]({author_url}) moved protection settings from {redirect}*{article}* to [{target}]({target_url}){comment}").format(author=author, author_url=author_url, redirect="⤷ " if "redirect" in change else "", article=change["logparams"]["oldtitle_title"],
			target=change["title"], target_url=link, comment=parsed_comment)
	elif action == "block/block":
		user = change["title"].split(':', 1)[1]
		restriction_description = ""
		try:
			ipaddress.ip_address(user)
			link = link_formatter(create_article_path("Special:Contributions/{user}".format(user=user), WIKI_ARTICLE_PATH))
		except ValueError:
			link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		if change["logparams"]["duration"] in ["infinite", "indefinite", "infinity", "never"]:
			block_time = _("for infinity and beyond")
		else:
			english_length = re.sub(r"(\d+)", "", change["logparams"][
				"duration"])  # note that translation won't work for millenia and century yet
			english_length_num = re.sub(r"(\D+)", "", change["logparams"]["duration"])
			try:
				if "@" in english_length:
					raise ValueError
				english_length = english_length.rstrip("s").strip()
				try:
					block_time = _("for {num} {translated_length}").format(num=english_length_num,
				                                                translated_length=ngettext(english_length,
				                                                                           english_length + "s",
				                                                                           int(english_length_num)))
				except ValueError:
					logger.exception("Couldn't properly resolve block expiry.")
			except (AttributeError, ValueError):
				date_time_obj = datetime.datetime.strptime(change["logparams"]["expiry"], '%Y-%m-%dT%H:%M:%SZ')
				block_time = _("until {}").format(date_time_obj.strftime("%Y-%m-%d %H:%M:%S UTC"))
			if "sitewide" not in change["logparams"]:
				if "restrictions" in change["logparams"]:
					if "pages" in change["logparams"]["restrictions"] and change["logparams"]["restrictions"]["pages"]:
						restriction_description = _(" on pages: ")
						for page in change["logparams"]["restrictions"]["pages"]:
							restricted_pages = ["*{page}*".format(page=i["page_title"]) for i in change["logparams"]["restrictions"]["pages"]]
						restriction_description = restriction_description + ", ".join(restricted_pages)
					if "namespaces" in change["logparams"]["restrictions"] and change["logparams"]["restrictions"]["namespaces"]:
						namespaces = []
						if restriction_description:
							restriction_description = restriction_description + _(" and namespaces: ")
						else:
							restriction_description = _(" on namespaces: ")
						for namespace in change["logparams"]["restrictions"]["namespaces"]:
							if str(namespace) in additional_data.namespaces:  # if we have cached namespace name for given namespace number, add its name to the list
								namespaces.append("*{ns}*".format(ns=additional_data.namespaces[str(namespace)]["*"]))
							else:
								namespaces.append("*{ns}*".format(ns=namespace))
						restriction_description = restriction_description + ", ".join(namespaces)
					restriction_description = restriction_description + "."
					if len(restriction_description) > 1020:
						logger.debug(restriction_description)
						restriction_description = restriction_description[:1020] + "…"
		content = _(
			"[{author}]({author_url}) blocked [{user}]({user_url}) {time}{restriction_desc}{comment}").format(author=author, author_url=author_url, user=user, time=block_time, user_url=link, restriction_desc=restriction_description, comment=parsed_comment)
	elif action == "block/reblock":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		user = change["title"].split(':', 1)[1]
		content = _("[{author}]({author_url}) changed block settings for [{blocked_user}]({user_url}){comment}").format(author=author, author_url=author_url, blocked_user=user, user_url=link, comment=parsed_comment)
	elif action == "block/unblock":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		user = change["title"].split(':', 1)[1]
		content = _("[{author}]({author_url}) unblocked [{blocked_user}]({user_url}){comment}").format(author=author, author_url=author_url, blocked_user=user, user_url=link, comment=parsed_comment)
	elif action == "curseprofile/comment-created":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		target_user = change["title"].split(':', 1)[1]
		if target_user != author:
			content = _("[{author}]({author_url}) left a [comment]({comment}) on {target}'s profile".format(author=author, author_url=author_url, comment=link, target=target_user))
		else:
			content = _("[{author}]({author_url}) left a [comment]({comment}) on their own profile".format(author=author, author_url=author_url, comment=link))
	elif action == "curseprofile/comment-replied":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		target_user = change["title"].split(':', 1)[1]
		if target_user != author:
			content = _(
				"[{author}]({author_url}) replied to a [comment]({comment}) on {target}'s profile".format(author=author,
				                                                                                    author_url=author_url,
				                                                                                    comment=link,
				                                                                                    target=target_user))
		else:
			content = _(
				"[{author}]({author_url}) replied to a [comment]({comment}) on their own profile".format(author=author,
				                                                                                   comment=link,
				                                                                                   author_url=author_url))
	elif action == "curseprofile/comment-edited":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		target_user = change["title"].split(':', 1)[1]
		if target_user != author:
			content = _(
				"[{author}]({author_url}) edited a [comment]({comment}) on {target}'s profile".format(author=author,
				                                                                                          author_url=author_url,
				                                                                                          comment=link,
				                                                                                          target=target_user))
		else:
			content = _(
				"[{author}]({author_url}) edited a [comment]({comment}) on their own profile".format(author=author,
				                                                                                         comment=link,
				                                                                                         author_url=author_url))
	elif action == "curseprofile/comment-purged":
		target_user = change["title"].split(':', 1)[1]
		if target_user != author:
			content = _("[{author}]({author_url}) purged a comment on {target}'s profile".format(author=author, author_url=author_url,target=target_user))
		else:
			content = _("[{author}]({author_url}) purged a comment on their own profile".format(author=author, author_url=author_url))
	elif action == "curseprofile/comment-deleted":
		if "4:comment_id" in change["logparams"]:
			link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		else:
			link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		target_user = change["title"].split(':', 1)[1]
		if target_user != author:
			content = _("[{author}]({author_url}) deleted a [comment]({comment}) on {target}'s profile".format(author=author,author_url=author_url, comment=link, target=target_user))
		else:
			content = _("[{author}]({author_url}) deleted a [comment]({comment}) on their own profile".format(author=author, author_url=author_url, comment=link))

	elif action == "curseprofile/profile-edited":
		target_user = change["title"].split(':', 1)[1]
		link = link_formatter(create_article_path("UserProfile:{user}".format(user=target_user), WIKI_ARTICLE_PATH))
		if target_user != author:
			content = _("[{author}]({author_url}) edited the {field} on [{target}]({target_url})'s profile. *({desc})*").format(author=author,
				                                                                author_url=author_url,
				                                                                target=target_user,
				                                                                target_url=link,
				                                                                field=profile_field_name(change["logparams"]['4:section'], False, message_target[0][0]),
				                                                                desc=BeautifulSoup(change["parsedcomment"], "lxml").get_text())
		else:
			content = _("[{author}]({author_url}) edited the {field} on [their own]({target_url}) profile. *({desc})*").format(
				author=author,
				author_url=author_url,
				target_url=link,
				field=profile_field_name(change["logparams"]['4:section'], False, message_target[0][0]),
				desc=BeautifulSoup(change["parsedcomment"], "lxml").get_text())
	elif action in ("rights/rights", "rights/autopromote"):
		link = link_formatter(create_article_path("User:{user}".format(user=change["title"].split(":")[1]), WIKI_ARTICLE_PATH))
		old_groups = []
		new_groups = []
		for name in change["logparams"]["oldgroups"]:
			old_groups.append(_(name))
		for name in change["logparams"]["newgroups"]:
			new_groups.append(_(name))
		if len(old_groups) == 0:
			old_groups = [_("none")]
		if len(new_groups) == 0:
			new_groups = [_("none")]

		if action == "rights/rights":
			content = _("[{author}]({author_url}) changed group membership for [{target}]({target_url}) from {old_groups} to {new_groups}{comment}").format(author=author, author_url=author_url, target=change["title"].split(":")[1], target_url=link, old_groups=", ".join(old_groups), new_groups=', '.join(new_groups), comment=parsed_comment)
		else:
			content = _("{author} autopromoted [{target}]({target_url}) from {old_groups} to {new_groups}{comment}").format(
				author=_("System"), author_url=author_url, target=change["title"].split(":")[1], target_url=link,
				old_groups=", ".join(old_groups), new_groups=', '.join(new_groups),
				comment=parsed_comment)
	elif action == "protect/protect":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) protected [{article}]({article_url}) with the following settings: {settings}{comment}").format(author=author, author_url=author_url,
		                                                                                                                                     article=change["title"], article_url=link,
		                                                                                                                                     settings=change["logparams"].get("description", "")+(_(" [cascading]") if "cascade" in change["logparams"] else ""),
		                                                                                                                                     comment=parsed_comment)
	elif action == "protect/modify":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _(
			"[{author}]({author_url}) modified protection settings of [{article}]({article_url}) to: {settings}{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			settings=change["logparams"].get("description", "") + (_(" [cascading]") if "cascade" in change["logparams"] else ""),
			comment=parsed_comment)
	elif action == "protect/unprotect":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) removed protection from [{article}]({article_url}){comment}").format(author=author, author_url=author_url, article=change["title"], article_url=link, comment=parsed_comment)
	elif action == "delete/revision":
		amount = len(change["logparams"]["ids"])
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = ngettext("[{author}]({author_url}) changed visibility of revision on page [{article}]({article_url}){comment}",
		                          "[{author}]({author_url}) changed visibility of {amount} revisions on page [{article}]({article_url}){comment}", amount).format(author=author, author_url=author_url,
			article=change["title"], article_url=link, amount=amount, comment=parsed_comment)
	elif action == "import/upload":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = ngettext("[{author}]({author_url}) imported [{article}]({article_url}) with {count} revision{comment}",
		                          "[{author}]({author_url}) imported [{article}]({article_url}) with {count} revisions{comment}", change["logparams"]["count"]).format(
			author=author, author_url=author_url, article=change["title"], article_url=link, count=change["logparams"]["count"], comment=parsed_comment)
	elif action == "delete/restore":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) restored [{article}]({article_url}){comment}").format(author=author, author_url=author_url, article=change["title"], article_url=link, comment=parsed_comment)
	elif action == "delete/event":
		content = _("[{author}]({author_url}) changed visibility of log events{comment}").format(author=author, author_url=author_url, comment=parsed_comment)
	elif action == "import/interwiki":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		source_link = link_formatter(create_article_path(change["logparams"]["interwiki_title"], WIKI_ARTICLE_PATH))
		content = ngettext("[{author}]({author_url}) imported [{article}]({article_url}) with {count} revision from [{source}]({source_url}){comment}",
		                          "[{author}]({author_url}) imported [{article}]({article_url}) with {count} revisions from [{source}]({source_url}){comment}", change["logparams"]["count"]).format(
			author=author, author_url=author_url, article=change["title"], article_url=link, count=change["logparams"]["count"], source=change["logparams"]["interwiki_title"], source_url=source_link, comment=parsed_comment)
	elif action == "abusefilter/modify":
		link = link_formatter(create_article_path("Special:AbuseFilter/history/{number}/diff/prev/{historyid}".format(number=change["logparams"]['newId'], historyid=change["logparams"]["historyId"]), WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) edited abuse filter [number {number}]({filter_url})").format(author=author, author_url=author_url, number=change["logparams"]['newId'], filter_url=link)
	elif action == "abusefilter/create":
		link = link_formatter(
			create_article_path("Special:AbuseFilter/{number}".format(number=change["logparams"]['newId']), WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) created abuse filter [number {number}]({filter_url})").format(author=author, author_url=author_url, number=change["logparams"]['newId'], filter_url=link)
	elif action == "merge/merge":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		link_dest = link_formatter(create_article_path(change["logparams"]["dest_title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) merged revision histories of [{article}]({article_url}) into [{dest}]({dest_url}){comment}").format(author=author, author_url=author_url, article=change["title"], article_url=link, dest_url=link_dest,
		                                                                                dest=change["logparams"]["dest_title"], comment=parsed_comment)
	elif action == "newusers/autocreate":
		content = _("Account [{author}]({author_url}) was created automatically").format(author=author, author_url=author_url)
	elif action == "newusers/create":
		content = _("Account [{author}]({author_url}) was created").format(author=author, author_url=author_url)
	elif action == "newusers/create2":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("Account [{article}]({article_url}) was created by [{author}]({author_url}){comment}").format(article=change["title"], article_url=link, author=author, author_url=author_url, comment=parsed_comment)
	elif action == "newusers/byemail":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("Account [{article}]({article_url}) was created by [{author}]({author_url}) and password was sent by email{comment}").format(article=change["title"], article_url=link, author=author, author_url=author_url, comment=parsed_comment)
	elif action == "newusers/newusers":
		content = _("Account [{author}]({author_url}) was created").format(author=author, author_url=author_url)
	elif action == "interwiki/iw_add":
		link = link_formatter(create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) added an entry to the [interwiki table]({table_url}) pointing to {website} with {prefix} prefix").format(author=author, author_url=author_url, desc=parsed_comment,
		                                                                           prefix=change["logparams"]['0'],
		                                                                           website=change["logparams"]['1'],
		                                                                            table_url=link)
	elif action == "interwiki/iw_edit":
		link = link_formatter(create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) edited an entry in [interwiki table]({table_url}) pointing to {website} with {prefix} prefix").format(author=author, author_url=author_url, desc=parsed_comment,
		                                                                           prefix=change["logparams"]['0'],
		                                                                           website=change["logparams"]['1'],
		                                                                            table_url=link)
	elif action == "interwiki/iw_delete":
		link = link_formatter(create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deleted an entry in [interwiki table]({table_url})").format(author=author, author_url=author_url, table_url=link)
	elif action == "contentmodel/change":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) changed the content model of the page [{article}]({article_url}) from {old} to {new}{comment}").format(author=author, author_url=author_url, article=change["title"], article_url=link, old=change["logparams"]["oldmodel"],
		                                                                         new=change["logparams"]["newmodel"], comment=parsed_comment)
	elif action == "contentmodel/new":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) created the page [{article}]({article_url}) using a non-default content model {new}{comment}").format(author=author, author_url=author_url, article=change["title"], article_url=link, new=change["logparams"]["newmodel"], comment=parsed_comment)
	elif action == "sprite/sprite":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) edited the sprite for [{article}]({article_url})").format(author=author, author_url=author_url, article=change["title"], article_url=link)
	elif action == "sprite/sheet":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) created the sprite sheet for [{article}]({article_url})").format(author=author, author_url=author_url, article=change["title"], article_url=link)
	elif action == "sprite/slice":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) edited the slice for [{article}]({article_url})").format(author=author, author_url=author_url, article=change["title"], article_url=link)
	elif action == "cargo/createtable":
		table = parse_link(paths[3], change["logparams"]["0"])
		content = _("[{author}]({author_url}) created the Cargo table \"{table}\"").format(author=author, author_url=author_url, table=table)
	elif action == "cargo/deletetable":
		content = _("[{author}]({author_url}) deleted the Cargo table \"{table}\"").format(author=author, author_url=author_url, table=change["logparams"]["0"])
	elif action == "cargo/recreatetable":
		table = parse_link(paths[3], change["logparams"]["0"])
		content = _("[{author}]({author_url}) recreated the Cargo table \"{table}\"").format(author=author, author_url=author_url, table=table)
	elif action == "cargo/replacetable":
		table = parse_link(paths[3], change["logparams"]["0"])
		content = _("[{author}]({author_url}) replaced the Cargo table \"{table}\"").format(author=author, author_url=author_url, table=table)
	elif action == "managetags/create":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) created the [tag]({tag_url}) \"{tag}\"{comment}").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link, comment=parsed_comment)
	elif action == "managetags/delete":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		if change["logparams"]["count"] == 0:
			content = _("[{author}]({author_url}) deleted the [tag]({tag_url}) \"{tag}\"{comment}").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link, comment=parsed_comment)
		else:
			content = ngettext("[{author}]({author_url}) deleted the [tag]({tag_url}) \"{tag}\" and removed it from {count} revision or log entry{comment}",
		                       "[{author}]({author_url}) deleted the [tag]({tag_url}) \"{tag}\" and removed it from {count} revisions and/or log entries{comment}",
		                       change["logparams"]["count"]).format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link, count=change["logparams"]["count"], comment=parsed_comment)
	elif action == "managetags/activate":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) activated the [tag]({tag_url}) \"{tag}\"{comment}").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link, comment=parsed_comment)
	elif action == "managetags/deactivate":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deactivated the [tag]({tag_url}) \"{tag}\"{comment}").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link, comment=parsed_comment)
	elif action == "managewiki/settings":  # Miraheze's ManageWiki extension https://github.com/miraheze/ManageWiki
		content = _(
			"[{author}]({author_url}) changed wiki settings{reason}".format(author=author, author_url=author_url,
			                                                                   reason=parsed_comment))
	elif action == "managewiki/delete":
		content = _("[{author}]({author_url}) deleted a wiki *{wiki_name}*{comment}").format(author=author, author_url=author_url,
		                                                                                              wiki_name=change["logparams"].get("wiki", _("Unknown")), comment=parsed_comment)
	elif action == "managewiki/lock":
		content = _("[{author}]({author_url}) locked a wiki *{wiki_name}*{comment}").format(
			author=author, author_url=author_url, wiki_name=change["logparams"].get("wiki", _("Unknown")), comment=parsed_comment)
	elif action == "managewiki/namespaces":
		content = _("[{author}]({author_url}) modified a namespace *{namespace_name}* on *{wiki_name}*{comment}").format(
			author=author, author_url=author_url, namespace_name=change["logparams"].get("namespace", _("Unknown")),
		    wiki_name=change["logparams"].get("wiki", _("Unknown")), comment=parsed_comment)
	elif action == "managewiki/namespaces-delete":
		content = _(
			"[{author}]({author_url}) deleted a namespace *{namespace_name}* on *{wiki_name}*{comment}").format(
			author=author, author_url=author_url,
			namespace_name=change["logparams"].get("namespace", _("Unknown")),
			wiki_name=change["logparams"].get("wiki", _("Unknown")), comment=parsed_comment)
	elif action == "managewiki/rights":
		group_name = change["title"].split("/permissions/", 1)[1]
		content = _("[{author}]({author_url}) modified user group *{group_name}*{comment}").format(
			author=author, author_url=author_url, group_name=group_name, comment=parsed_comment
		)
	elif action == "managewiki/undelete":
		content = _("[{author}]({author_url}) undeleted a wiki *{wiki_name}*{comment}").format(
			author=author, author_url=author_url, wiki_name=change["logparams"].get("wiki", _("Unknown")), comment=parsed_comment
		)
	elif action == "managewiki/unlock":
		content = _("[{author}]({author_url}) unlocked a wiki *{wiki_name}*{comment}").format(
			author=author, author_url=author_url, wiki_name=change["logparams"].get("wiki", _("Unknown")),
			comment=parsed_comment
		)
	elif action == "datadump/generate":
		content = _("[{author}]({author_url}) generated *{file}* dump{comment}").format(
			author=author, author_url=author_url, file=change["logparams"]["filename"],
			comment=parsed_comment
		)
	elif action == "datadump/delete":
		content = _("[{author}]({author_url}) deleted *{file}* dump{comment}").format(
			author=author, author_url=author_url, file=change["logparams"]["filename"],
			comment=parsed_comment
		)
	elif action == "pagetranslation/mark":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if "?" in link:
			link = link + "&oldid={}".format(change["logparams"]["revision"])
		else:
			link = link + "?oldid={}".format(change["logparams"]["revision"])
		link = link_formatter(link)
		content = _("[{author}]({author_url}) marked [{article}]({article_url}) for translation{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/unmark":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) removed [{article}]({article_url}) from the translation system{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/moveok":
		link = link_formatter(create_article_path(change["logparams"]["target"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) completed moving translation pages from *{article}* to [{target}]({target_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], target=change["logparams"]["target"], target_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/movenok":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		target_url = link_formatter(create_article_path(change["logparams"]["target"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) encountered a problem while moving [{article}]({article_url}) to [{target}]({target_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			target=change["logparams"]["target"], target_url=target_url,
			comment=parsed_comment
		)
	elif action == "pagetranslation/deletefok":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) completed deletion of translatable page [{article}]({article_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/deletefnok":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		target_url = link_formatter(create_article_path(change["logparams"]["target"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) failed to delete [{article}]({article_url}) which belongs to translatable page [{target}]({target_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			target=change["logparams"]["target"], target_url=target_url,
			comment=parsed_comment
		)
	elif action == "pagetranslation/deletelok":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) completed deletion of translation page [{article}]({article_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/deletelnok":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		target_url = link_formatter(create_article_path(change["logparams"]["target"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) failed to delete [{article}]({article_url}) which belongs to translation page [{target}]({target_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			target=change["logparams"]["target"], target_url=target_url,
			comment=parsed_comment
		)
	elif action == "pagetranslation/encourage":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) encouraged translation of [{article}]({article_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/discourage":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) discouraged translation of [{article}]({article_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "pagetranslation/prioritylanguages":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		if "languages" in change["logparams"]:
			languages = "`, `".join(change["logparams"]["languages"].split(","))
			if change["logparams"]["force"] == "on":
				content = _("[{author}]({author_url}) limited languages for [{article}]({article_url}) to `{languages}`{comment}").format(
					author=author, author_url=author_url,
					article=change["title"], article_url=link,
					languages=languages, comment=parsed_comment
				)
			else:
				content = _("[{author}]({author_url}) set the priority languages for [{article}]({article_url}) to `{languages}`{comment}").format(
					author=author, author_url=author_url,
					article=change["title"], article_url=link,
					languages=languages, comment=parsed_comment
				)
		else:
			content = _("[{author}]({author_url}) removed priority languages from [{article}]({article_url}){comment}").format(
				author=author, author_url=author_url,
				article=change["title"], article_url=link,
				comment=parsed_comment
			)
	elif action == "pagetranslation/associate":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) added translatable page [{article}]({article_url}) to aggregate group \"{group}\"{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			group=change["logparams"]["aggregategroup"], comment=parsed_comment
		)
	elif action == "pagetranslation/dissociate":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) removed translatable page [{article}]({article_url}) from aggregate group \"{group}\"{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			group=change["logparams"]["aggregategroup"], comment=parsed_comment
		)
	elif action == "translationreview/message":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if "?" in link:
			link = link + "&oldid={}".format(change["logparams"]["revision"])
		else:
			link = link + "?oldid={}".format(change["logparams"]["revision"])
		link = link_formatter(link)
		content = _("[{author}]({author_url}) reviewed translation [{article}]({article_url}){comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			comment=parsed_comment
		)
	elif action == "translationreview/group":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		if "old-state" in change["logparams"]:
			content = _("[{author}]({author_url}) changed the state of `{language}` translations of [{article}]({article_url}) from `{old_state}` to `{new_state}`{comment}").format(
				author=author, author_url=author_url, language=change["logparams"]["language"],
				article=change["logparams"]["group-label"], article_url=link,
				old_state=change["logparams"]["old-state"], new_state=change["logparams"]["new-state"],
				comment=parsed_comment
			)
		else:
			content = _("[{author}]({author_url}) changed the state of `{language}` translations of [{article}]({article_url}) to `{new_state}`{comment}").format(
				author=author, author_url=author_url, language=change["logparams"]["language"],
				article=change["logparams"]["group-label"], article_url=link,
				new_state=change["logparams"]["new-state"], comment=parsed_comment
			)
	elif action == "pagelang/pagelang":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		old_lang = "`{}`".format(change["logparams"]["oldlanguage"])
		if change["logparams"]["oldlanguage"][-5:] == "[def]":
			old_lang = "`{}` {}".format(change["logparams"]["oldlanguage"][:-5], _("(default)"))
		new_lang = "`{}`".format(change["logparams"]["newlanguage"])
		if change["logparams"]["newlanguage"][-5:] == "[def]":
			new_lang = "`{}` {}".format(change["logparams"]["oldlanguage"][:-5], _("(default)"))
		content = _("[{author}]({author_url}) changed the language of [{article}]({article_url}) from {old_lang} to {new_lang}{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			old_lang=old_lang, new_lang=new_lang, comment=parsed_comment
		)
	elif action == "renameuser/renameuser":
		link = link_formatter(create_article_path("User:"+change["logparams"]["newuser"], WIKI_ARTICLE_PATH))
		edits = change["logparams"]["edits"]
		if edits > 0:
			content = ngettext("[{author}]({author_url}) renamed user *{old_name}* with {edits} edit to [{new_name}]({link}){comment}",
			                          "[{author}]({author_url}) renamed user *{old_name}* with {edits} edits to [{new_name}]({link}){comment}", edits).format(
				author=author, author_url=author_url, old_name=change["logparams"]["olduser"], edits=edits, new_name=change["logparams"]["newuser"], link=link, comment=parsed_comment
			)
		else:
			content = _("[{author}]({author_url}) renamed user *{old_name}* to [{new_name}]({link}){comment}").format(
				author=author, author_url=author_url, old_name=change["logparams"]["olduser"], new_name=change["logparams"]["newuser"], link=link, comment=parsed_comment
			)
	elif action == "suppressed":
		content = _("An action has been hidden by administration.")
	else:
		logger.warning("No entry for {event} with params: {params}".format(event=action, params=change))
		if not settings.get("support", None):
			return
		else:
			content = _("Unknown event `{event}` by [{author}]({author_url}), report it on the [support server](<{support}>).").format(event=action, author=author, author_url=author_url, support=settings["support"])
			action = "unknown"
	return DiscordMessage("compact", action, message_target[1], content=content, wiki=WIKI_SCRIPT_PATH)


async def embed_formatter(action, change, parsed_comment, categories, recent_changes, message_target, paths, rate_limiter, additional_data=None) -> DiscordMessage:
	"""Recent Changes embed formatter, part of RcGcDw"""
	_ = langs[message_target[0][0]]["rc_formatters"].gettext
	ngettext = langs[message_target[0][0]]["rc_formatters"].ngettext
	if additional_data is None:
		additional_data = {"namespaces": {}, "tags": {}}
	WIKI_API_PATH = paths[0]
	WIKI_SCRIPT_PATH = paths[1]
	WIKI_ARTICLE_PATH = paths[2]
	WIKI_JUST_DOMAIN = paths[3]
	embed = DiscordMessage("embed", action, message_target[1], wiki=WIKI_SCRIPT_PATH)
	if parsed_comment is None:
		parsed_comment = _("No description provided")
	if action != "suppressed":
		if "anon" in change:
			author_url = create_article_path("Special:Contributions/{user}".format(user=change["user"]), WIKI_ARTICLE_PATH)
		else:
			author_url = create_article_path("User:{}".format(change["user"]), WIKI_ARTICLE_PATH)
		embed.set_author(change["user"], author_url)
	if action in ("edit", "new"):  # edit or new page
		editsize = change["newlen"] - change["oldlen"]
		if editsize > 0:
			if editsize > 6032:
				embed["color"] = 65280
			else:
				embed["color"] = 35840 + (math.floor(editsize / 52)) * 256
		elif editsize < 0:
			if editsize < -6032:
				embed["color"] = 16711680
			else:
				embed["color"] = 9175040 + (math.floor((editsize * -1) / 52)) * 65536
		elif editsize == 0:
			embed["color"] = 8750469
		link = "{wiki}index.php?title={article}&curid={pageid}&diff={diff}&oldid={oldrev}".format(
			wiki=WIKI_SCRIPT_PATH, pageid=change["pageid"], diff=change["revid"], oldrev=change["old_revid"],
			article=change["title"].replace(" ", "_").replace("%", "%25").replace("\\", "%5C").replace("&", "%26"))
		embed["title"] = "{redirect}{article} ({new}{minor}{bot}{space}{editsize})".format(redirect="⤷ " if "redirect" in change else "", article=change["title"], editsize="+" + str(
			editsize) if editsize > 0 else editsize, new=_("(N!) ") if action == "new" else "",
		                                                             minor=_("m") if action == "edit" and "minor" in change else "", bot=_('b') if "bot" in change else "", space=" " if "bot" in change or (action == "edit" and "minor" in change) or action == "new" else "")
		if message_target[0][1] == 3:
			if action == "new":
				changed_content = await recent_changes.safe_request(
				"{wiki}?action=compare&format=json&fromtext=&torev={diff}&topst=1&prop=diff".format(
					wiki=WIKI_API_PATH, diff=change["revid"]
				), rate_limiter, "compare", "*")
			else:
				changed_content = await recent_changes.safe_request(
					"{wiki}?action=compare&format=json&fromrev={oldrev}&torev={diff}&topst=1&prop=diff".format(
						wiki=WIKI_API_PATH, diff=change["revid"],oldrev=change["old_revid"]
					), rate_limiter, "compare", "*")
			if changed_content:
				EditDiff = ContentParser(message_target[0][0])
				EditDiff.feed(changed_content)
				if EditDiff.small_prev_del:
					if EditDiff.small_prev_del.replace("~~", "").isspace():
						EditDiff.small_prev_del = _('__Only whitespace__')
					else:
						EditDiff.small_prev_del = EditDiff.small_prev_del.replace("~~~~", "")
				if EditDiff.small_prev_ins:
					if EditDiff.small_prev_ins.replace("**", "").isspace():
						EditDiff.small_prev_ins = _('__Only whitespace__')
					else:
						EditDiff.small_prev_ins = EditDiff.small_prev_ins.replace("****", "")
				logger.debug("Changed content: {}".format(EditDiff.small_prev_ins))
				if EditDiff.small_prev_del and not action == "new":
					embed.add_field(_("Removed"), "{data}".format(data=EditDiff.small_prev_del), inline=True)
				if EditDiff.small_prev_ins:
					embed.add_field(_("Added"), "{data}".format(data=EditDiff.small_prev_ins), inline=True)
			else:
				logger.warning("Unable to download data on the edit content!")
	elif action in ("upload/overwrite", "upload/upload", "upload/revert"):  # sending files
		license = None
		try:
			urls = await recent_changes.safe_request(
			"{wiki}?action=query&format=json&prop=imageinfo&list=&meta=&titles={filename}&iiprop=timestamp%7Curl%7Carchivename&iilimit=5".format(
				wiki=WIKI_API_PATH, filename=change["title"]), rate_limiter, "query", "pages")
		except ClientResponseError:
			# We could do this in safe_request but I don't know how that would affect other requests,
			# prefer to have handling in here instead. When this happens, simply ignore the image preview
			urls = None
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		additional_info_retrieved = False
		if urls is not None:
			logger.debug(urls)
			if "-1" not in urls:  # image still exists and not removed
				try:
					img_info = next(iter(urls.values()))["imageinfo"]
					for num, revision in enumerate(img_info):
						if revision["timestamp"] == change["logparams"]["img_timestamp"]:  # find the correct revision corresponding for this log entry
							image_direct_url = "{rev}?{cache}".format(rev=revision["url"], cache=int(time.time()*5))  # cachebusting
							additional_info_retrieved = True
							break
				except KeyError:
					logger.warning("Wiki did not respond with extended information about file. The preview will not be shown.")
		else:
			logger.warning("Request for additional image information have failed. The preview will not be shown.")
		if action in ("upload/overwrite", "upload/revert"):
			if additional_info_retrieved:
				article_encoded = change["title"].replace(" ", "_").replace("%", "%25").replace("\\", "%5C").replace("&", "%26").replace(')', '\\)')
				try:
					revision = img_info[num+1]
				except IndexError:
					logger.exception("Could not analize the information about the image (does it have only one version when expected more in overwrite?) which resulted in no Options field: {}".format(img_info))
				else:
					undolink = "{wiki}index.php?title={filename}&action=revert&oldimage={archiveid}".format(
						wiki=WIKI_SCRIPT_PATH, filename=article_encoded, archiveid=revision["archivename"])
					embed.add_field(_("Options"), _("([preview]({link}) | [undo]({undolink}))").format(
						link=image_direct_url, undolink=undolink))
				if message_target[0][1] > 1:
					embed["image"]["url"] = image_direct_url
			if action == "upload/overwrite":
				embed["title"] = _("Uploaded a new version of {name}").format(name=change["title"])
			elif action == "upload/revert":
				embed["title"] = _("Reverted a version of {name}").format(name=change["title"])
		else:
			embed["title"] = _("Uploaded {name}").format(name=change["title"])
			if additional_info_retrieved:
				embed.add_field(_("Options"), _("([preview]({link}))").format(link=image_direct_url))
				if message_target[0][1] > 1:
					embed["image"]["url"] = image_direct_url
	elif action == "delete/delete":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted page {article}").format(article=change["title"])
	elif action == "delete/delete_redir":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted redirect {article} by overwriting").format(article=change["title"])
	elif action == "move/move":
		link = create_article_path(change["logparams"]['target_title'], WIKI_ARTICLE_PATH)
		parsed_comment = "{supress}. {desc}".format(desc=parsed_comment,
		                                            supress=_("No redirect has been made") if "suppressredirect" in change["logparams"] else _(
			                                            "A redirect has been made"))
		embed["title"] = _("Moved {redirect}{article} to {target}").format(redirect="⤷ " if "redirect" in change else "", article=change["title"], target=change["logparams"]['target_title'])
	elif action == "move/move_redir":
		link = create_article_path(change["logparams"]["target_title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Moved {redirect}{article} to {title} over redirect").format(redirect="⤷ " if "redirect" in change else "", article=change["title"],
		                                                                      title=change["logparams"]["target_title"])
	elif action == "protect/move_prot":
		link = create_article_path(change["logparams"]["oldtitle_title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Moved protection settings from {redirect}{article} to {title}").format(redirect="⤷ " if "redirect" in change else "", article=change["logparams"]["oldtitle_title"],
		                                                                                 title=change["title"])
	elif action == "block/block":
		user = change["title"].split(':', 1)[1]
		try:
			ipaddress.ip_address(user)
			link = create_article_path("Special:Contributions/{user}".format(user=user), WIKI_ARTICLE_PATH)
		except ValueError:
			link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if change["logparams"]["duration"] in ["infinite", "indefinite", "infinity", "never"]:
			block_time = _("for infinity and beyond")
		else:
			english_length = re.sub(r"(\d+)", "", change["logparams"]["duration"])  # note that translation won't work for millenia and century yet
			english_length_num = re.sub(r"(\D+)", "", change["logparams"]["duration"])
			try:
				if "@" in english_length:
					raise ValueError
				english_length = english_length.rstrip("s").strip()
				block_time = _("for {num} {translated_length}").format(num=english_length_num, translated_length=ngettext(english_length, english_length + "s", int(english_length_num)))
			except (AttributeError, ValueError):
				if "expiry" in change["logparams"]:
					date_time_obj = datetime.datetime.strptime(change["logparams"]["expiry"], '%Y-%m-%dT%H:%M:%SZ')
					block_time = _("until {}").format(date_time_obj.strftime("%Y-%m-%d %H:%M:%S UTC"))
				else:
					block_time = _("unknown expiry time")  # THIS IS HERE JUST TEMPORARY AS A HOT FIX TO #157, will be changed with release of 1.13
		if "sitewide" not in change["logparams"]:
			restriction_description = ""
			if "restrictions" in change["logparams"]:
				if "pages" in change["logparams"]["restrictions"] and change["logparams"]["restrictions"]["pages"]:
					restriction_description = _("Blocked from editing the following pages: ")
					for page in change["logparams"]["restrictions"]["pages"]:
						restricted_pages = ["*"+i["page_title"]+"*" for i in change["logparams"]["restrictions"]["pages"]]
					restriction_description = restriction_description + ", ".join(restricted_pages)
				if "namespaces" in change["logparams"]["restrictions"] and change["logparams"]["restrictions"]["namespaces"]:
					namespaces = []
					if restriction_description:
						restriction_description = restriction_description + _(" and namespaces: ")
					else:
						restriction_description = _("Blocked from editing pages on following namespaces: ")
					for namespace in change["logparams"]["restrictions"]["namespaces"]:
						if str(namespace) in additional_data.namespaces:  # if we have cached namespace name for given namespace number, add its name to the list
							namespaces.append("*{ns}*".format(ns=additional_data.namespaces[str(namespace)]["*"]))
						else:
							namespaces.append("*{ns}*".format(ns=namespace))
					restriction_description = restriction_description + ", ".join(namespaces)
				restriction_description = restriction_description + "."
				if len(restriction_description) > 1020:
					logger.debug(restriction_description)
					restriction_description = restriction_description[:1020]+"…"
				embed.add_field(_("Partial block details"), restriction_description, inline=True)
		embed["title"] = _("Blocked {blocked_user} {time}").format(blocked_user=user, time=block_time)
	elif action == "block/reblock":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		user = change["title"].split(':', 1)[1]
		embed["title"] = _("Changed block settings for {blocked_user}").format(blocked_user=user)
	elif action == "block/unblock":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		user = change["title"].split(':', 1)[1]
		embed["title"] = _("Unblocked {blocked_user}").format(blocked_user=user)
	elif action == "curseprofile/comment-created":
		if message_target[0][1] == 3:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		target_user = change["title"].split(':', 1)[1]
		if target_user != change["user"]:
			embed["title"] = _("Left a comment on {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Left a comment on their own profile")
	elif action == "curseprofile/comment-replied":
		if message_target[0][1] == 3:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		target_user = change["title"].split(':', 1)[1]
		if target_user != change["user"]:
			embed["title"] = _("Replied to a comment on {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Replied to a comment on their own profile")
	elif action == "curseprofile/comment-edited":
		if message_target[0][1] == 3:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		target_user = change["title"].split(':', 1)[1]
		if target_user != change["user"]:
			embed["title"] = _("Edited a comment on {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Edited a comment on their own profile")
	elif action == "curseprofile/profile-edited":
		target_user = change["title"].split(':', 1)[1]
		link = create_article_path("UserProfile:{target}".format(target=target_user), WIKI_ARTICLE_PATH)
		if target_user != change["user"]:
			embed["title"] = _("Edited {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Edited their own profile")
		if not change["parsedcomment"]:  # If the field is empty
			parsed_comment = _("Cleared the {field} field").format(field=profile_field_name(change["logparams"]['4:section'], True, message_target[0][0]))
		else:
			parsed_comment = _("{field} field changed to: {desc}").format(field=profile_field_name(change["logparams"]['4:section'], True, message_target[0][0]), desc=BeautifulSoup(change["parsedcomment"], "lxml").get_text())
	elif action == "curseprofile/comment-purged":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		target_user = change["title"].split(':', 1)[1]
		if target_user != change["user"]:
			embed["title"] = _("Purged a comment on {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Purged a comment on their own profile")
	elif action == "curseprofile/comment-deleted":
		if "4:comment_id" in change["logparams"]:
			link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		else:
			link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		target_user = change["title"].split(':', 1)[1]
		if target_user != change["user"]:
			embed["title"] = _("Deleted a comment on {target}'s profile").format(target=target_user)
		else:
			embed["title"] = _("Deleted a comment on their own profile")
	elif action in ("rights/rights", "rights/autopromote"):
		link = create_article_path("User:{}".format(change["title"].split(":")[1]), WIKI_ARTICLE_PATH)
		if action == "rights/rights":
			embed["title"] = _("Changed group membership for {target}").format(target=change["title"].split(":")[1])
		else:
			author_url = ""
			embed.set_author(_("System"), author_url)
			embed["title"] = _("{target} got autopromoted to a new usergroup").format(
				target=change["title"].split(":")[1])
		if len(change["logparams"]["oldgroups"]) < len(change["logparams"]["newgroups"]):
			embed["thumbnail"]["url"] = "https://i.imgur.com/WnGhF5g.gif"
		old_groups = []
		new_groups = []
		for name in change["logparams"]["oldgroups"]:
			old_groups.append(_(name))
		for name in change["logparams"]["newgroups"]:
			new_groups.append(_(name))
		if len(old_groups) == 0:
			old_groups = [_("none")]
		if len(new_groups) == 0:
			new_groups = [_("none")]
		reason = ": {desc}".format(desc=parsed_comment) if parsed_comment != _("No description provided") else ""
		parsed_comment = _("Groups changed from {old_groups} to {new_groups}{reason}").format(
			old_groups=", ".join(old_groups), new_groups=', '.join(new_groups), reason=reason)
	elif action == "protect/protect":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Protected {target}").format(target=change["title"])
		parsed_comment = "{settings}{cascade} | {reason}".format(settings=change["logparams"].get("description", ""),
		                                                         cascade=_(" [cascading]") if "cascade" in change["logparams"] else "",
		                                                         reason=parsed_comment)
	elif action == "protect/modify":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed protection level for {article}").format(article=change["title"])
		parsed_comment = "{settings}{cascade} | {reason}".format(settings=change["logparams"].get("description", ""),
		                                                         cascade=_(" [cascading]") if "cascade" in change["logparams"] else "",
		                                                         reason=parsed_comment)
	elif action == "protect/unprotect":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Removed protection from {article}").format(article=change["title"])
	elif action == "delete/revision":
		amount = len(change["logparams"]["ids"])
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = ngettext("Changed visibility of revision on page {article} ",
		                          "Changed visibility of {amount} revisions on page {article} ", amount).format(
			article=change["title"], amount=amount)
	elif action == "import/upload":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = ngettext("Imported {article} with {count} revision",
		                          "Imported {article} with {count} revisions", change["logparams"]["count"]).format(
			article=change["title"], count=change["logparams"]["count"])
	elif action == "delete/restore":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Restored {article}").format(article=change["title"])
	elif action == "delete/event":
		link = create_article_path("Special:RecentChanges", WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed visibility of log events")
	elif action == "import/interwiki":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = ngettext("Imported {article} with {count} revision from \"{source}\"",
		                          "Imported {article} with {count} revisions from \"{source}\"", change["logparams"]["count"]).format(
			article=change["title"], count=change["logparams"]["count"], source=change["logparams"]["interwiki_title"])
	elif action == "abusefilter/modify":
		link = create_article_path("Special:AbuseFilter/history/{number}/diff/prev/{historyid}".format(number=change["logparams"]['newId'], historyid=change["logparams"]["historyId"]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited abuse filter number {number}").format(number=change["logparams"]['newId'])
	elif action == "abusefilter/create":
		link = create_article_path("Special:AbuseFilter/{number}".format(number=change["logparams"]['newId']), WIKI_ARTICLE_PATH)
		embed["title"] = _("Created abuse filter number {number}").format(number=change["logparams"]['newId'])
	elif action == "merge/merge":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Merged revision histories of {article} into {dest}").format(article=change["title"],
		                                                                                dest=change["logparams"]["dest_title"])
	elif action == "newusers/autocreate":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created account automatically")
	elif action == "newusers/create":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created account")
	elif action == "newusers/create2":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created account {article}").format(article=change["title"])
	elif action == "newusers/byemail":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created account {article} and password was sent by email").format(article=change["title"])
	elif action == "newusers/newusers":
		link = author_url
		embed["title"] = _("Created account")
	elif action == "interwiki/iw_add":
		link = create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH)
		embed["title"] = _("Added an entry to the interwiki table")
		parsed_comment = _("Prefix: {prefix}, website: {website} | {desc}").format(desc=parsed_comment,
		                                                                           prefix=change["logparams"]['0'],
		                                                                           website=change["logparams"]['1'])
	elif action == "interwiki/iw_edit":
		link = create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited an entry in interwiki table")
		parsed_comment = _("Prefix: {prefix}, website: {website} | {desc}").format(desc=parsed_comment,
		                                                                           prefix=change["logparams"]['0'],
		                                                                           website=change["logparams"]['1'])
	elif action == "interwiki/iw_delete":
		link = create_article_path("Special:Interwiki", WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted an entry in interwiki table")
		parsed_comment = _("Prefix: {prefix} | {desc}").format(desc=parsed_comment, prefix=change["logparams"]['0'])
	elif action == "contentmodel/change":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed the content model of the page {article}").format(article=change["title"])
		parsed_comment = _("Model changed from {old} to {new}: {reason}").format(old=change["logparams"]["oldmodel"],
		                                                                         new=change["logparams"]["newmodel"],
		                                                                         reason=parsed_comment)
	elif action == "contentmodel/new":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created the page {article} using a non-default content model").format(article=change["title"])
		parsed_comment = _("Created with model {new}: {reason}").format(new=change["logparams"]["newmodel"], reason=parsed_comment)
	elif action == "sprite/sprite":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited the sprite for {article}").format(article=change["title"])
	elif action == "sprite/sheet":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created the sprite sheet for {article}").format(article=change["title"])
	elif action == "sprite/slice":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited the slice for {article}").format(article=change["title"])
	elif action == "cargo/createtable":
		table = re.search(r"\[(.*?)\]\(<(.*?)>\)", parse_link(paths[3], change["logparams"]["0"]))
		link = table.group(2)
		embed["title"] = _("Created the Cargo table \"{table}\"").format(table=table.group(1))
		parsed_comment = None
	elif action == "cargo/deletetable":
		link = create_article_path("Special:CargoTables", WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted the Cargo table \"{table}\"").format(table=change["logparams"]["0"])
		parsed_comment = None
	elif action == "cargo/recreatetable":
		table = re.search(r"\[(.*?)\]\(<(.*?)>\)", parse_link(paths[3], change["logparams"]["0"]))
		link = table.group(2)
		embed["title"] = _("Recreated the Cargo table \"{table}\"").format(table=table.group(1))
		parsed_comment = None
	elif action == "cargo/replacetable":
		table = re.search(r"\[(.*?)\]\(<(.*?)>\)", parse_link(paths[3], change["logparams"]["0"]))
		link = table.group(2)
		embed["title"] = _("Replaced the Cargo table \"{table}\"").format(table=table.group(1))
		parsed_comment = None
	elif action == "managetags/create":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Created the tag \"{tag}\"").format(tag=change["logparams"]["tag"])
	elif action == "managetags/delete":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted the tag \"{tag}\"").format(tag=change["logparams"]["tag"])
		if change["logparams"]["count"] > 0:
			embed.add_field(_('Removed from'), ngettext("{} revision or log entry", "{} revisions and/or log entries", change["logparams"]["count"]).format(change["logparams"]["count"]))
	elif action == "managetags/activate":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Activated the tag \"{tag}\"").format(tag=change["logparams"]["tag"])
	elif action == "managetags/deactivate":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Deactivated the tag \"{tag}\"").format(tag=change["logparams"]["tag"])
	elif action == "managewiki/settings":  # Miraheze's ManageWiki extension https://github.com/miraheze/ManageWiki
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed wiki settings")
		if change["logparams"].get("changes", ""):
			embed.add_field("Setting", change["logparams"].get("changes"))
	elif action == "managewiki/delete":
		embed["title"] = _("Deleted a \"{wiki}\" wiki").format(wiki=change["logparams"].get("wiki", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "managewiki/lock":
		embed["title"] = _("Locked a \"{wiki}\" wiki").format(wiki=change["logparams"].get("wiki", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "managewiki/namespaces":
		embed["title"] = _("Modified a \"{namespace_name}\" namespace").format(namespace_name=change["logparams"].get("namespace", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed.add_field(_('Wiki'), change["logparams"].get("wiki", _("Unknown")))
	elif action == "managewiki/namespaces-delete":
		embed["title"] = _("Deleted a \"{namespace_name}\" namespace").format(
				namespace_name=change["logparams"].get("namespace", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed.add_field(_('Wiki'), change["logparams"].get("wiki", _("Unknown")))
	elif action == "managewiki/rights":
		group_name = change["title"].split("/permissions/", 1)[1]
		embed["title"] = _("Modified \"{usergroup_name}\" usergroup").format(usergroup_name=group_name)
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "managewiki/undelete":
		embed["title"] = _("Undeleted a \"{wiki}\" wiki").format(wiki=change["logparams"].get("wiki", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "managewiki/unlock":
		embed["title"] = _("Unlocked a \"{wiki}\" wiki").format(wiki=change["logparams"].get("wiki", _("Unknown")))
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "datadump/generate":
		embed["title"] = _("Generated {file} dump").format(file=change["logparams"]["filename"])
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "datadump/delete":
		embed["title"] = _("Deleted {file} dump").format(file=change["logparams"]["filename"])
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
	elif action == "pagetranslation/mark":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if "?" in link:
			link = link + "&oldid={}".format(change["logparams"]["revision"])
		else:
			link = link + "?oldid={}".format(change["logparams"]["revision"])
		embed["title"] = _("Marked \"{article}\" for translation").format(article=change["title"])
	elif action == "pagetranslation/unmark":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Removed \"{article}\" from the translation system").format(article=change["title"])
	elif action == "pagetranslation/moveok":
		link = create_article_path(change["logparams"]["target"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Completed moving translation pages from \"{article}\" to \"{target}\"").format(article=change["title"], target=change["logparams"]["target"])
	elif action == "pagetranslation/movenok":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Encountered a problem while moving \"{article}\" to \"{target}\"").format(article=change["title"], target=change["logparams"]["target"])
	elif action == "pagetranslation/deletefok":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Completed deletion of translatable page \"{article}\"").format(article=change["title"])
	elif action == "pagetranslation/deletefnok":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Failed to delete \"{article}\" which belongs to translatable page \"{target}\"").format(article=change["title"], target=change["logparams"]["target"])
	elif action == "pagetranslation/deletelok":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Completed deletion of translation page \"{article}\"").format(article=change["title"])
	elif action == "pagetranslation/deletelnok":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Failed to delete \"{article}\" which belongs to translation page \"{target}\"").format(article=change["title"], target=change["logparams"]["target"])
	elif action == "pagetranslation/encourage":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Encouraged translation of \"{article}\"").format(article=change["title"])
	elif action == "pagetranslation/discourage":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Discouraged translation of \"{article}\"").format(article=change["title"])
	elif action == "pagetranslation/prioritylanguages":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if "languages" in change["logparams"]:
			languages = "`, `".join(change["logparams"]["languages"].split(","))
			if change["logparams"]["force"] == "on":
				embed["title"] = _("Limited languages for \"{article}\" to `{languages}`").format(article=change["title"], languages=languages)
			else:
				embed["title"] = _("Priority languages for \"{article}\" set to `{languages}`").format(article=change["title"], languages=languages)
		else:
			embed["title"] = _("Removed priority languages from \"{article}\"").format(article=change["title"])
	elif action == "pagetranslation/associate":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Added translatable page \"{article}\" to aggregate group \"{group}\"").format(article=change["title"], group=change["logparams"]["aggregategroup"])
	elif action == "pagetranslation/dissociate":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Removed translatable page \"{article}\" from aggregate group \"{group}\"").format(article=change["title"], group=change["logparams"]["aggregategroup"])
	elif action == "translationreview/message":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		if "?" in link:
			link = link + "&oldid={}".format(change["logparams"]["revision"])
		else:
			link = link + "?oldid={}".format(change["logparams"]["revision"])
		embed["title"] = _("Reviewed translation \"{article}\"").format(article=change["title"])
	elif action == "translationreview/group":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed the state of `{language}` translations of \"{article}\"").format(language=change["logparams"]["language"], article=change["title"])
		if "old-state" in change["logparams"]:
			embed.add_field(_("Old state"), change["logparams"]["old-state"], inline=True)
		embed.add_field(_("New state"), change["logparams"]["new-state"], inline=True)
	elif action == "pagelang/pagelang":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		old_lang = "`{}`".format(change["logparams"]["oldlanguage"])
		if change["logparams"]["oldlanguage"][-5:] == "[def]":
			old_lang = "`{}` {}".format(change["logparams"]["oldlanguage"][:-5], _("(default)"))
		new_lang = "`{}`".format(change["logparams"]["newlanguage"])
		if change["logparams"]["newlanguage"][-5:] == "[def]":
			new_lang = "`{}` {}".format(change["logparams"]["oldlanguage"][:-5], _("(default)"))
		embed["title"] = _("Changed the language of \"{article}\"").format(article=change["title"])
		embed.add_field(_("Old language"), old_lang, inline=True)
		embed.add_field(_("New language"), new_lang, inline=True)
	elif action == "renameuser/renameuser":
		edits = change["logparams"]["edits"]
		if edits > 0:
			embed["title"] = ngettext("Renamed user \"{old_name}\" with {edits} edit to \"{new_name}\"", "Renamed user \"{old_name}\" with {edits} edits to \"{new_name}\"", edits).format(old_name=change["logparams"]["olduser"], edits=edits, new_name=change["logparams"]["newuser"])
		else:
			embed["title"] = _("Renamed user \"{old_name}\" to \"{new_name}\"").format(old_name=change["logparams"]["olduser"], new_name=change["logparams"]["newuser"])
		link = create_article_path("User:"+change["logparams"]["newuser"], WIKI_ARTICLE_PATH)
	elif action == "suppressed":
		link = create_article_path("", WIKI_ARTICLE_PATH)
		embed.set_author(_("Unknown"))
	else:
		logger.warning("No entry for {event} with params: {params}".format(event=action, params=change))
		link = create_article_path("Special:RecentChanges", WIKI_ARTICLE_PATH)
		embed["title"] = _("Unknown event `{event}`").format(event=action)
		embed.event_type = "unknown"
		if settings.get("support", None):
			change_params = "[```json\n{params}\n```]({support})".format(params=json.dumps(change, indent=2), support=settings["support"])
			if len(change_params) > 1000:
				embed.add_field(_("Report this on the support server"), settings["support"])
			else:
				embed.add_field(_("Report this on the support server"), change_params)
	embed["url"] = link
	if parsed_comment is not None:
		embed["description"] = parsed_comment
	embed["timestamp"] = change["timestamp"]
	if "tags" in change and change["tags"]:
		tag_displayname = []
		for tag in change["tags"]:
			if tag in additional_data["tags"]:
				if additional_data["tags"][tag] is None:
					continue  # Ignore hidden tags
				else:
					tag_displayname.append(additional_data["tags"][tag])
			else:
				tag_displayname.append(tag)
		embed.add_field(_("Tags"), ", ".join(tag_displayname))
	if len(embed["title"]) > 254:
		embed["title"] = embed["title"][0:253]+"…"
	logger.debug("Current params in edit action: {}".format(change))
	if categories and not (len(categories["new"]) == 0 and len(categories["removed"]) == 0):
		new_cat = (_("**Added**: ") + ", ".join(list(categories["new"])[0:16]) + ("\n" if len(categories["new"])<=15 else _(" and {} more\n").format(len(categories["new"])-15))) if categories["new"] else ""
		del_cat = (_("**Removed**: ") + ", ".join(list(categories["removed"])[0:16]) + ("" if len(categories["removed"])<=15 else _(" and {} more").format(len(categories["removed"])-15))) if categories["removed"] else ""
		embed.add_field(_("Changed categories"), new_cat + del_cat)
	embed.finish_embed()
	return embed
