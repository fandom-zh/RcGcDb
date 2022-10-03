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

import ipaddress
import logging
from src.discord.message import DiscordMessage
from src.api import formatter
from src.api.context import Context
from src.api.util import embed_helper, sanitize_to_url, parse_mediawiki_changes, clean_link, compact_author, sanitize_to_markdown

# Order results from most drastic first to less drastic last
abuselog_results = ["degroup", "blockautopromote", "rangeblock", "block", "disallow", "throttle", "warn", "tag", ""]
abusefilter_results = lambda string, _, default: {"degroup": _("**Removed from privileged groups**"), "blockautopromote": _("Removed autoconfirmed group"), "rangeblock": _("**IP range blocked**"), "block": _("**Blocked user**"), "disallow": _("Disallowed the action"), "throttle": _("Throttled actions"), "warn": _("Warning issued"), "tag": _("Tagged the edit"), "": _("None")}.get(string, default)
abusefilter_actions = lambda string, _, default: {"edit": _("Edit"), "upload": _("Upload"), "move": _("Move"), "stashupload": _("Stash upload"), "delete": _("Deletion"), "createaccount": _("Account creation"), "autocreateaccount": _("Auto account creation")}.get(string, default)

logger = logging.getLogger("extensions.base")

# AbuseFilter - https://www.mediawiki.org/wiki/Special:MyLanguage/Extension:AbuseFilter
# Processing Abuselog LOG events, separate from RC logs


def abuselog_action(results):
	action = "unknown"
	for result in abuselog_results:
		if result in results:
			action = "abuselog/{}".format(result)
			break
	return action


def abuse_filter_format_user(change, settings):
	author = change["user"]
	if settings.get("hide_ips", False):
		try:
			ipaddress.ip_address(change["user"])
		except ValueError:
			pass
		else:
			author = _("Unregistered user")
	return author


@formatter.embed(event="abuselog")
def embed_abuselog(ctx: Context, change: dict):
	results = change["result"].split(",")
	action = abuselog_action(results)
	embed = DiscordMessage(ctx.message_type, action, ctx.webhook_url)
	author = abuse_filter_format_user(change, ctx.settings)
	embed["title"] = ctx._("{user} triggered \"{abuse_filter}\"").format(user=author, abuse_filter=sanitize_to_markdown(change["filter"]))
	embed.add_field(ctx._("Performed"), abusefilter_actions(change["action"], ctx._, change["action"]))
	embed.add_field(ctx._("Title"), sanitize_to_markdown(change.get("title", ctx._("Unknown"))))
	embed.add_field(ctx._("Action taken"), ctx._(", ").join([abusefilter_results(result, ctx._, result) for result in results]))
	return embed


@formatter.compact(event="abuselog")
def compact_abuselog(ctx: Context, change: dict):
	results = change["result"].split(",")
	action = abuselog_action(results)
	author_url = clean_link(ctx.client.create_article_path("User:{user}".format(user=change["user"])))
	author = abuse_filter_format_user(change, ctx.settings)
	message = ctx._("[{author}]({author_url}) triggered *{abuse_filter}*, performing the action \"{action}\" on *[{target}]({target_url})* - action taken: {result}.").format(
		author=author, author_url=author_url, abuse_filter=sanitize_to_markdown(change["filter"]),
		action=abusefilter_actions(change["action"], ctx._, change["action"]), target=change.get("title", ctx._("Unknown")),
		target_url=clean_link(ctx.client.create_article_path(sanitize_to_url(change.get("title", ctx._("Unknown"))))),
		result=ctx._(", ").join([abusefilter_results(result, ctx._, result) for result in results]))
	return DiscordMessage(ctx.message_type, action, ctx.webhook_url, content=message)

# abusefilter/modify - AbuseFilter filter modification


@formatter.embed(event="abusefilter/modify")
def embed_abuselog_modify(ctx: Context, change: dict):
	embed = DiscordMessage(ctx.message_type, ctx.event, ctx.webhook_url)
	embed_helper(ctx, embed, change)
	embed["url"] = ctx.client.create_article_path(
		"Special:AbuseFilter/history/{number}/diff/prev/{historyid}".format(number=change["logparams"]['newId'],
																			historyid=change["logparams"]["historyId"]))
	embed["title"] = ctx._("Edited abuse filter number {number}").format(number=change["logparams"]['newId'])
	return embed


@formatter.compact(event="abusefilter/modify")
def compact_abuselog_modify(ctx: Context, change: dict):
	author, author_url = compact_author(ctx, change)
	link = clean_link(ctx.client.create_article_path(
		"Special:AbuseFilter/history/{number}/diff/prev/{historyid}".format(number=change["logparams"]['newId'],
																			historyid=change["logparams"][
																				"historyId"])))

	content = ctx._("[{author}]({author_url}) edited abuse filter [number {number}]({filter_url})").format(author=author,
																									   author_url=author_url,
																									   number=change[
																										   "logparams"][
																										   'newId'],
																									   filter_url=link)
	return DiscordMessage(ctx.message_type, ctx.event, ctx.webhook_url, content=content)

# abusefilter/create - AbuseFilter filter creation


@formatter.embed(event="abusefilter/create")
def embed_abuselog_create(ctx: Context, change: dict):
	embed = DiscordMessage(ctx.message_type, ctx.event, ctx.webhook_url)
	embed_helper(ctx, embed, change)
	embed["url"] = ctx.client.create_article_path("Special:AbuseFilter/{number}".format(number=change["logparams"]['newId']))
	embed["title"] = ctx._("Created abuse filter number {number}").format(number=change["logparams"]['newId'])
	return embed


@formatter.compact(event="abusefilter/create")
def compact_abuselog_create(ctx: Context, change: dict):
	author, author_url = compact_author(ctx, change)
	link = clean_link(
		ctx.client.create_article_path("Special:AbuseFilter/{number}".format(number=change["logparams"]['newId'])))
	content = ctx._("[{author}]({author_url}) created abuse filter [number {number}]({filter_url})").format(author=author,
																										author_url=author_url,
																										number=change[
																											"logparams"][
																											'newId'],
																										filter_url=link)
	return DiscordMessage(ctx.message_type, ctx.event, ctx.webhook_url, content=content)
