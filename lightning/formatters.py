"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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

from datetime import datetime

import discord


def codeblock(text: str, *, language: str = "py") -> str:
    return f"```{language}\n{text}```"


def truncate_text(text: str, limit: int, *, suffix: str = "...") -> str:
    if len(text) < limit:
        return text
    return text[:limit - len(suffix)] + suffix


# plural, human_join use code provided by Rapptz under the MIT License
# © 2015 Rapptz
# https://github.com/Rapptz/RoboDanny/blob/6fd16002e0cbd3ed68bf5a8db10d61658b0b9d51/cogs/utils/formats.py
class plural:  # noqa
    def __init__(self, value):
        self.value = value

    def __format__(self, format_spec):
        v = self.value
        singular, sep, plural = format_spec.partition('|')
        plural = plural or f'{singular}s'
        if abs(v) != 1:
            return f'{v} {plural}'
        return f'{v} {singular}'


def human_join(seq, delim=', ', conj='or') -> str:
    size = len(seq)
    if size == 0:
        return ''

    if size == 1:
        return seq[0]

    if size == 2:
        return f'{seq[0]} {conj} {seq[1]}'

    return delim.join(seq[:-1]) + f' {conj} {seq[-1]}'


# These live here (instead of in modlogformats) so lightning.events can use them without
# importing the renderers, which import the events. That's what would cause a circular import.
def escape_markdown_and_mentions(text) -> str:
    """Helper function to escape mentions and markdown from a string

    Parameters
    ----------
    text : str
        The string to remove markdown and mentions from

    Returns
    -------
    str
        The escaped text
    """
    escaped_markdown = discord.utils.escape_markdown(text)
    return discord.utils.escape_mentions(escaped_markdown)


def action_format(author, action_text="Action done by", *, reason=None) -> str:
    if reason is None:
        return f"{action_text} {str(author)} (ID: {author.id})"
    else:
        return f"{str(author)} (ID: {author.id}): {reason}"


def base_user_format(user, unknown_text="Unknown user with ID: ") -> str:
    if hasattr(user, 'name'):
        return f"{escape_markdown_and_mentions(str(user))} ({user.id})"
    else:
        return f"{unknown_text}{user.id if hasattr(user, 'id') else user}"


def format_timestamp(dt: datetime) -> str:
    return discord.utils.format_dt(dt, style="T")


def construct_dm_message(member, action_verb, location, *, middle=None, reason=None, ending=None):
    msg = [f"You were {action_verb} {location} {member.guild.name}"]
    if middle:
        msg.append(middle)
    if reason:
        msg.append(f"\n\n**Reason**: {reason}")
    if ending:
        msg.append(f"\n{ending}")
    return ''.join(msg)
