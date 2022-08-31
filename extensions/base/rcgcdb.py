import logging
import json
from src.discord.message import DiscordMessage
from src.api import formatter
from src.api.context import Context
from src.api.util import embed_helper, compact_author, create_article_path, sanitize_to_markdown


@formatter.embed(event="generic")
def embed_generic(ctx: Context, change: dict):
    embed = DiscordMessage(ctx.message_type, ctx.event)
    embed_helper(ctx, embed, change)
    embed["title"] = ctx._("Unknown event `{event}`").format(
        event="{type}/{action}".format(type=change.get("type", ""), action=change.get("action", "")))
    embed["url"] = create_article_path("Special:RecentChanges")
    change_params = "[```json\n{params}\n```]({support})".format(params=json.dumps(change, indent=2),
                                                                 support=ctx.settings["support"])
    if len(change_params) > 1000:
        embed.add_field(_("Report this on the support server"), ctx.settings["support"])
    else:
        embed.add_field(_("Report this on the support server"), change_params)
    return embed


@formatter.compact(event="generic")
def compact_generic(ctx: Context, change: dict):
    author, author_url = compact_author(ctx, change)
    content = ctx._("Unknown event `{event}` by [{author}]({author_url}), report it on the [support server](<{support}>).").format(
        event="{type}/{action}".format(type=change.get("type", ""), action=change.get("action", "")),
        author=author, support=ctx.settings["support"], author_url=author_url)
    return DiscordMessage(ctx.message_type, ctx.event, content=content)
