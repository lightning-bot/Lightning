"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from typing import Annotated, Optional

import discord
from discord.ext import commands

from lightning import flags
from lightning.converters import Snowflake

BaseModParser = flags.FlagParser([flags.Flag("--nodm", "--no-dm", is_bool_flag=True,
                                             help="Bot does not DM the user the reason for the action."),
                                  flags.Flag(attribute="reason", consume_rest=True)],
                                 raise_on_bad_flag=False)


class PurgeFlags(commands.FlagConverter, prefix="--", delimiter=""):
    attachments: Optional[bool] = commands.flag(default=None, description="Remove messages that contain attachments")
    before: Annotated[Optional[int], Snowflake] = commands.flag(default=None,
                                                                description="Search for messages before this message"
                                                                            " ID")
    after: Annotated[Optional[int], Snowflake] = commands.flag(default=None,
                                                               description="Search for messages after this message ID")
    user: Optional[discord.Member] = commands.flag(default=None, description="Remove messages from the specified user")
    bots: Optional[bool] = commands.flag(default=None, description="Removes messages from bots")
