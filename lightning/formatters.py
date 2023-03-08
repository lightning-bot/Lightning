"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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


def codeblock(text: str, *, language: str = "py") -> str:
    return f"```{language}\n{text}```"


def truncate_text(text: str, limit: int, *, suffix: str = "...") -> str:
    return text if len(text) < limit else text[:limit - len(suffix)] + suffix


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
        return f'{v} {plural}' if abs(v) != 1 else f'{v} {singular}'


def human_join(seq, delim=', ', conj='or') -> str:
    size = len(seq)
    if size == 0:
        return ''

    if size == 1:
        return seq[0]

    if size == 2:
        return f'{seq[0]} {conj} {seq[1]}'

    return f'{delim.join(seq[:-1])} {conj} {seq[-1]}'
