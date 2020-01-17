# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import re
from utils.errors import LightningError
from utils.time import plural


def boolean_flags(flags: list, text: str, raise_errors=True, flag_aliases: dict = None):
    """A flag parser that marks any matching flags as a boolean.

    Arguments
    ---------
    flags: list
        A list of flags you want to find.

    text: str
        String of text.

    raise_errors: bool
        Whether to raise `LightningError` if an invalid flag is passed.
        Defaults to True.

    flag_aliases: dict
        An optional dict of aliases for flags.
        Dict should be constructed as {flagalias: flagname}.
    Returns
    -------
    dict containing flags and text stripped of flags and whitespace
    """
    split_text = re.compile(r'(\S+)').split(text)
    info = {"text": None}
    for flag in flags:
        info[flag] = False
    if flag_aliases is not None:
        flags += list(flag_aliases.keys())
    for word in iter(split_text):
        try:
            if word[0] == "-":
                if word not in flags:
                    if raise_errors is True:
                        raise LightningError("Invalid flag passed. "
                                             f"Expected {', '.join(flags)} {plural(len(flags)):flag}")
                    continue
                if word in flag_aliases if flag_aliases else None:
                    info[flag_aliases[word]] = True
                elif word in info:
                    info[word] = True
                split_text.remove(word)
        except IndexError:
            continue
    info['text'] = ''.join(split_text)
    # Strip text
    info['text'] = info['text'].strip()
    return info
