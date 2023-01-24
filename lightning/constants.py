"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import re
from typing import Literal

COMMON_HOIST_CHARACTERS = ["!", "-", "/", "*", "(", ")", "+", "[", "]", "#", "<", ">", "_", ".", "$", "\"", "?", "'"]


class Emoji:
    greentick = "<:greenTick:613702930444451880>"
    redtick = "<:redTick:613703043283681290>"
    member_leave = "<:member_leave:613363354357989376>"
    member_join = "<:member_join:613361413272109076>"
    python = "<:python:605592693267103744>"
    dpy = "<:dpy:617883851162779648>"
    postgres = "<:postgres:617886426318635015>"
    bot_tag = "<:bot_tag:1067547599026012170>"
    # Presence emojis
    do_not_disturb = "<:dnd:572962188134842389>"
    online = "<:online:572962188114001921>"
    idle = "<:idle:572962188201820200>"
    offline = "<:offline:572962188008882178>"
    numbers = ('1\N{combining enclosing keycap}',
               '2\N{combining enclosing keycap}',
               '3\N{combining enclosing keycap}',
               '4\N{combining enclosing keycap}',
               '5\N{combining enclosing keycap}',
               '6\N{combining enclosing keycap}',
               '7\N{combining enclosing keycap}',
               '8\N{combining enclosing keycap}',
               '9\N{combining enclosing keycap}',
               '\N{KEYCAP TEN}')


# Human-readable names
AUTOMOD_EVENT_NAMES_MAPPING = {"message-spam": "Message Spam",
                               "mass-mentions": "Mass Mentions",
                               "url-spam": "URL Spam",
                               "invite-spam": "Invite Spam",
                               "message-content-spam": "Repetitive Message Spam"}
AUTOMOD_EVENT_NAMES = list(AUTOMOD_EVENT_NAMES_MAPPING.keys())
AUTOMOD_EVENT_NAMES_LITERAL = Literal['message-spam', 'mass-mentions', 'url-spam', 'invite-spam',
                                      'message-content-spam']

AUTOMOD_COMMAND_CONFIG_REGEX = re.compile(r"(?P<count>[0-9]+)/(?P<seconds>[0-9]+)s")
