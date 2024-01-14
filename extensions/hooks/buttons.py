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
from typing import Optional

from src.api.context import Context
from src.discord.message import DiscordMessage, DiscordMessageMetadata
from src.api.hook import post_hook

# The webhook used for RcGcDb need to be controlled by a Discord application running https://github.com/Markus-Rost/rcgcdw-buttons
# You can use https://www.wikibot.de/interactions to create a Discord webhook to be used for RcGcDw that supports buttons.
# {
#     "hooks": {
#         "buttons": {
#             "block": "Block user",
#             "delete": "Delete",
#             "filerevert": "Revert",
#             "move": "Move back",
#             "rollback": "Rollback",
#             "undo": "Undo"
#         }
#     }
# }


def add_button(message: DiscordMessage, custom_id: str, label, style=2, emoji: Optional[dict] = None):
    if len(custom_id) > 100 or not len(label):
        return
    if "components" not in message.webhook_object:
        message.webhook_object["components"] = [{"type": 1, "components": []}]
    if len(message.webhook_object["components"][-1]["components"]) >= 5:
        message.webhook_object["components"].append({"type": 1, "components": []})
    message.webhook_object["components"][-1]["components"].append(
        {"type": 2, "custom_id": custom_id, "style": style, "label": label, "emoji": emoji})


@post_hook
def buttons_hook(message: DiscordMessage, metadata: DiscordMessageMetadata, context: Context, change: dict):
    action_buttons = context.buttons or ""
    if not len(action_buttons) or context.feed_type == "discussion":
        return
    BUTTON_PREFIX = context.client.WIKI_SCRIPT_PATH[len(context.client.WIKI_JUST_DOMAIN):]
    if "block" in action_buttons and context.event != "suppressed":
        add_button(message,
                   BUTTON_PREFIX + " block " + ("#" + str(change["userid"]) if change["userid"] else change["user"]),
                   context.gettext("Block user"), 4, {"id": None, "name": "🚧"})
    if context.feed_type != "recentchanges":
        return
    if "delete" in action_buttons and context.event in ("new", "upload/upload"):
        add_button(message, BUTTON_PREFIX + " delete " + str(change["pageid"]),
                   context.gettext("Delete"), 4, {"id": None, "name": "🗑️"})
    # if "filerevert" in action_buttons and context.event in ("upload/overwrite", "upload/revert"):
    #     add_button(message, BUTTON_PREFIX + " file " + str(change["pageid"]) + " " + revision["archivename"].split("!")[0],
    #         action_buttons["filerevert"], 2, {"id": None, "name": "🔂"})
    if "move" in action_buttons and context.event in ("move/move", "move/move_redir"):
        add_button(message, BUTTON_PREFIX + " move " + str(change["pageid"]) + " " + change["title"],
            context.gettext("Move back"), 2, {"id": None, "name": "🔂"})
    if context.event != "edit":
        return
    if "rollback" in action_buttons:
        add_button(message, BUTTON_PREFIX + " rollback " + str(change["pageid"]) + " " + (
            "#" + str(change["userid"]) if change["userid"] else change["user"]),
                   context.gettext("Rollback"), 1, {"id": None, "name": "🔁"})
    if "undo" in action_buttons:
        add_button(message, BUTTON_PREFIX + " undo " + str(change["pageid"]) + " " + str(change["revid"]),
            context.gettext("Undo"), 2, {"id": None, "name": "🔂"})
