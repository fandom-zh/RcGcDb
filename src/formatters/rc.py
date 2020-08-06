import ipaddress
import math
import re
import time
import json
import logging
import datetime
from src.config import settings
from src.misc import link_formatter, create_article_path, parse_link, profile_field_name, ContentParser
from src.discord import DiscordMessage
from src.msgqueue import send_to_discord

from bs4 import BeautifulSoup

logger = logging.getLogger("rcgcdw.rc_formatters")

if 1 == 2: # additional translation strings in unreachable code
	print(_("director"), _("bot"), _("editor"), _("directors"), _("sysop"), _("bureaucrat"), _("reviewer"),
	      _("autoreview"), _("autopatrol"), _("wiki_guardian"), ngettext("second", "seconds", 1), ngettext("minute", "minutes", 1), ngettext("hour", "hours", 1), ngettext("day", "days", 1), ngettext("week", "weeks", 1), ngettext("month", "months",1), ngettext("year", "years", 1), ngettext("millennium", "millennia", 1), ngettext("decade", "decades", 1), ngettext("century", "centuries", 1))

async def compact_formatter(action, change, parsed_comment, categories, recent_changes, message_target, _, ngettext, paths, rate_limiter,
                            additional_data=None):
	"""Recent Changes compact formatter, part of RcGcDw"""
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
		if edit_size > 0:
			sign = "+"
		else:
			sign = ""
		if change["title"].startswith("MediaWiki:Tag-"):
			pass
		if action == "edit":
			content = _("[{author}]({author_url}) edited [{article}]({edit_link}){comment} ({sign}{edit_size})").format(author=author, author_url=author_url, article=change["title"], edit_link=edit_link, comment=parsed_comment, edit_size=edit_size, sign=sign)
		else:
			content = _("[{author}]({author_url}) created [{article}]({edit_link}){comment} ({sign}{edit_size})").format(author=author, author_url=author_url, article=change["title"], edit_link=edit_link, comment=parsed_comment, edit_size=edit_size, sign=sign)
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
		if change["logparams"]["duration"] in ["infinite", "infinity"]:
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
				restriction_description = ""
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
		content = _("[{author}]({author_url}) left a [comment]({comment}) on {target} profile").format(author=author, author_url=author_url, comment=link, target=change["title"].split(':')[1]+"'s" if change["title"].split(':')[1] != change["user"] else _("their own profile"))
	elif action == "curseprofile/comment-replied":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) replied to a [comment]({comment}) on {target} profile").format(author=author,
		                                                                                               author_url=author_url,
		                                                                                               comment=link,
		                                                                                               target=change["title"].split(':')[1] if change["title"].split(':')[1] !=change["user"] else _("their own"))
	elif action == "curseprofile/comment-edited":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) edited a [comment]({comment}) on {target} profile").format(author=author,
		                                                                                               author_url=author_url,
		                                                                                               comment=link,
		                                                                                               target=change["title"].split(':')[1] if change["title"].split(':')[1] !=change["user"] else _("their own"))
	elif action == "curseprofile/comment-purged":
		link = link_formatter(create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) purged a comment on {target} profile").format(author=author,
		                                                                                     author_url=author_url,
		                                                                                     target=
		                                                                                     change["title"].split(':')[
			                                                                                     1] if
		                                                                                     change["title"].split(':')[
			                                                                                     1] != change[
			                                                                                     "user"] else _(
			                                                                                     "their own"))
	elif action == "curseprofile/comment-deleted":
		content = _("[{author}]({author_url}) deleted a comment on {target} profile").format(author=author,
		                                                                                    author_url=author_url,
		                                                                                     target=change["title"].split(':')[1] if change["title"].split(':')[1] !=change["user"] else _("their own"))

	elif action == "curseprofile/profile-edited":
		link = link_formatter(create_article_path("UserProfile:{user}".format(user=change["title"].split(":")[1]), WIKI_ARTICLE_PATH))
		target = _("[{target}]({target_url})'s").format(target=change["title"].split(':')[1], target_url=link) if change["title"].split(':')[1] != author else _("[their own]({target_url})").format(target_url=link)
		content = _("[{author}]({author_url}) edited the {field} on {target} profile. *({desc})*").format(author=author,
		                                                                        author_url=author_url,
		                                                                        target=target,
		                                                                        field=profile_field_name(change["logparams"]['4:section'], False, _),
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
			content = "[{author}]({author_url}) changed group membership for [{target}]({target_url}) from {old_groups} to {new_groups}{comment}".format(author=author, author_url=author_url, target=change["title"].split(":")[1], target_url=link, old_groups=", ".join(old_groups), new_groups=', '.join(new_groups), comment=parsed_comment)
		else:
			content = "{author} autopromoted [{target}]({target_url}) from {old_groups} to {new_groups}{comment}".format(
				author=_("System"), author_url=author_url, target=change["title"].split(":")[1], target_url=link,
				old_groups=", ".join(old_groups), new_groups=', '.join(new_groups),
				comment=parsed_comment)
	elif action == "protect/protect":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) protected [{article}]({article_url}) with the following settings: {settings}{comment}").format(author=author, author_url=author_url,
		                                                                                                                                     article=change["title"], article_url=link,
		                                                                                                                                     settings=change["logparams"]["description"]+_(" [cascading]") if "cascade" in change["logparams"] else "",
		                                                                                                                                     comment=parsed_comment)
	elif action == "protect/modify":
		link = link_formatter(create_article_path(change["title"], WIKI_ARTICLE_PATH))
		content = _(
			"[{author}]({author_url}) modified protection settings of [{article}]({article_url}) to: {settings}{comment}").format(
			author=author, author_url=author_url,
			article=change["title"], article_url=link,
			settings=change["logparams"]["description"] + _(" [cascading]") if "cascade" in change["logparams"] else "",
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
		content = _("[{author}]({author_url}) imported interwiki{comment}").format(author=author, author_url=author_url, comment=parsed_comment)
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
		link = link_formatter(create_article_path("Special:Tags", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) created a [tag]({tag_url}) \"{tag}\"").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link)
		recent_changes.init_info()
	elif action == "managetags/delete":
		link = link_formatter(create_article_path("Special:Tags", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deleted a [tag]({tag_url}) \"{tag}\"").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link)
		recent_changes.init_info()
	elif action == "managetags/activate":
		link = link_formatter(create_article_path("Special:Tags", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) activated a [tag]({tag_url}) \"{tag}\"").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link)
	elif action == "managetags/deactivate":
		link = link_formatter(create_article_path("Special:Tags", WIKI_ARTICLE_PATH))
		content = _("[{author}]({author_url}) deactivated a [tag]({tag_url}) \"{tag}\"").format(author=author, author_url=author_url, tag=change["logparams"]["tag"], tag_url=link)
	elif action == "suppressed":
		content = _("An action has been hidden by administration.")
	else:
		logger.warning("No entry for {event} with params: {params}".format(event=action, params=change))
		if not settings["support"]:
			return
		else:
			content = _("Unknown event `{event}` by [{author}]({author_url}), report it on the [support server](<{support}>).").format(event=action, author=author, author_url=author_url, support=settings["support"])
	await send_to_discord(DiscordMessage("compact", action, message_target[1], content=content, wiki=WIKI_SCRIPT_PATH))


async def embed_formatter(action, change, parsed_comment, categories, recent_changes, message_target, _, ngettext, paths, rate_limiter, additional_data=None):
	"""Recent Changes embed formatter, part of RcGcDw"""
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
		if change["title"].startswith("MediaWiki:Tag-"):  # Refresh tag list when tag display name is edited
			recent_changes.init_info()
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
				EditDiff = ContentParser(_)
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
		urls = await recent_changes.safe_request(
			"{wiki}?action=query&format=json&prop=imageinfo&list=&meta=&titles={filename}&iiprop=timestamp%7Curl%7Carchivename&iilimit=5".format(
				wiki=WIKI_API_PATH, filename=change["title"]), rate_limiter, "query", "pages")
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
				article_encoded = change["title"].replace(" ", "_").replace("%", "%25").replace("\\", "%5C").replace("&", "%26")
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
		if change["logparams"]["duration"] in ["infinite", "infinity"]:
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
				date_time_obj = datetime.datetime.strptime(change["logparams"]["expiry"], '%Y-%m-%dT%H:%M:%SZ')
				block_time = _("until {}").format(date_time_obj.strftime("%Y-%m-%d %H:%M:%S UTC"))
		if "sitewide" not in change["logparams"]:
			restriction_description = ""
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
		if settings["appearance"]["embed"]["show_edit_changes"]:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Left a comment on {target}'s profile").format(target=change["title"].split(':')[1]) if change["title"].split(':')[1] != \
		                                                                                              change["user"] else _(
			"Left a comment on their own profile")
	elif action == "curseprofile/comment-replied":
		if settings["appearance"]["embed"]["show_edit_changes"]:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Replied to a comment on {target}'s profile").format(target=change["title"].split(':')[1]) if change["title"].split(':')[1] != \
		                                                                                                    change["user"] else _(
			"Replied to a comment on their own profile")
	elif action == "curseprofile/comment-edited":
		if settings["appearance"]["embed"]["show_edit_changes"]:
			parsed_comment = await recent_changes.pull_comment(change["logparams"]["4:comment_id"], WIKI_API_PATH, rate_limiter)
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited a comment on {target}'s profile").format(target=change["title"].split(':')[1]) if change["title"].split(':')[1] != \
		                                                                                                change["user"] else _(
			"Edited a comment on their own profile")
	elif action == "curseprofile/profile-edited":
		link = create_article_path("UserProfile:{target}".format(target=change["title"].split(':')[1]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Edited {target}'s profile").format(target=change["title"].split(':')[1]) if change["user"] != change["title"].split(':')[1] else _("Edited their own profile")
		if not change["parsedcomment"]:  # If the field is empty
			parsed_comment = _("Cleared the {field} field").format(field=profile_field_name(change["logparams"]['4:section'], True, _))
		else:
			parsed_comment = _("{field} field changed to: {desc}").format(field=profile_field_name(change["logparams"]['4:section'], True, _), desc=BeautifulSoup(change["parsedcomment"], "lxml").get_text())
	elif action == "curseprofile/comment-purged":
		link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		embed["title"] = _("Purged a comment on {target}'s profile").format(target=change["title"].split(':')[1])
	elif action == "curseprofile/comment-deleted":
		if "4:comment_id" in change["logparams"]:
			link = create_article_path("Special:CommentPermalink/{commentid}".format(commentid=change["logparams"]["4:comment_id"]), WIKI_ARTICLE_PATH)
		else:
			link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted a comment on {target}'s profile").format(target=change["title"].split(':')[1])
	elif action in ("rights/rights", "rights/autopromote"):
		link = create_article_path("User:{}".format(change["title"].split(":")[1]), WIKI_ARTICLE_PATH)
		if action == "rights/rights":
			embed["title"] = _("Changed group membership for {target}").format(target=change["title"].split(":")[1])
		else:
			change["user"] = _("System")
			author_url = ""
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
		parsed_comment = "{settings}{cascade} | {reason}".format(settings=change["logparams"]["description"],
		                                                         cascade=_(" [cascading]") if "cascade" in change["logparams"] else "",
		                                                         reason=parsed_comment)
	elif action == "protect/modify":
		link = create_article_path(change["title"], WIKI_ARTICLE_PATH)
		embed["title"] = _("Changed protection level for {article}").format(article=change["title"])
		parsed_comment = "{settings}{cascade} | {reason}".format(settings=change["logparams"]["description"],
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
		link = create_article_path("Special:RecentChanges", WIKI_ARTICLE_PATH)
		embed["title"] = _("Imported interwiki")
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
		link = create_article_path("Special:Tags", WIKI_ARTICLE_PATH)
		embed["title"] = _("Created a tag \"{tag}\"").format(tag=change["logparams"]["tag"])
		recent_changes.init_info()
	elif action == "managetags/delete":
		link = create_article_path("Special:Tags", WIKI_ARTICLE_PATH)
		embed["title"] = _("Deleted a tag \"{tag}\"").format(tag=change["logparams"]["tag"])
		recent_changes.init_info()
	elif action == "managetags/activate":
		link = create_article_path("Special:Tags", WIKI_ARTICLE_PATH)
		embed["title"] = _("Activated a tag \"{tag}\"").format(tag=change["logparams"]["tag"])
	elif action == "managetags/deactivate":
		link = create_article_path("Special:Tags", WIKI_ARTICLE_PATH)
		embed["title"] = _("Deactivated a tag \"{tag}\"").format(tag=change["logparams"]["tag"])
	elif action == "suppressed":
		link = create_article_path("", WIKI_ARTICLE_PATH)
		embed["title"] = _("Action has been hidden by administration.")
		embed["author"]["name"] = _("Unknown")
	else:
		logger.warning("No entry for {event} with params: {params}".format(event=action, params=change))
		link = create_article_path("Special:RecentChanges", WIKI_ARTICLE_PATH)
		embed["title"] = _("Unknown event `{event}`").format(event=action)
		embed["color"] = 0
		if settings["support"]:
			change_params = "[```json\n{params}\n```]({support})".format(params=json.dumps(change, indent=2), support=settings["support"])
			if len(change_params) > 1000:
				embed.add_field(_("Report this on the support server"), settings["support"])
			else:
				embed.add_field(_("Report this on the support server"), change_params)
	embed["author"]["icon_url"] = settings["appearance"]["embed"].get(action, {"icon": None})["icon"]
	embed["url"] = link
	if parsed_comment is not None:
		embed["description"] = parsed_comment
	if settings["appearance"]["embed"]["show_footer"]:
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
	logger.debug("Current params in edit action: {}".format(change))
	if categories and not (len(categories["new"]) == 0 and len(categories["removed"]) == 0):
		new_cat = (_("**Added**: ") + ", ".join(list(categories["new"])[0:16]) + ("\n" if len(categories["new"])<=15 else _(" and {} more\n").format(len(categories["new"])-15))) if categories["new"] else ""
		del_cat = (_("**Removed**: ") + ", ".join(list(categories["removed"])[0:16]) + ("" if len(categories["removed"])<=15 else _(" and {} more").format(len(categories["removed"])-15))) if categories["removed"] else ""
		embed.add_field(_("Changed categories"), new_cat + del_cat)
	embed.finish_embed()
	await send_to_discord(embed)
