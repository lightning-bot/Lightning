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

from lightning.converters import Snowflake


class DefaultModFlags(commands.FlagConverter, prefix="--", delimiter=""):
    reason: Optional[str] = commands.flag(positional=True, default=None, description="The reason for the action")
    dm_user: Optional[bool] = commands.flag(name="dm", default=None,
                                            description="Whether to notify the user of the action or not "
                                            "(Overrides the guild settings)")


class BanFlags(commands.FlagConverter, prefix="--", delimiter=""):
    reason: Optional[str] = commands.flag(positional=True, default=None, description="The reason for the action")
    dm_user: Optional[bool] = commands.flag(name="dm", default=None,
                                            description="Whether to notify the user of the action or not "
                                            "(Overrides the guild settings)")
    delete_messages: int = commands.flag(aliases=['delete'], default=0,
                                         description="Delete message history from a specified amount of days (Max 7)")


class PurgeFlags(commands.FlagConverter, prefix="--", delimiter=""):
    attachments: Optional[bool] = commands.flag(default=None, description="Remove messages that contain attachments")
    before: Annotated[Optional[int], Snowflake] = commands.flag(default=None,
                                                                description="Search for messages before this message"
                                                                            " ID")
    after: Annotated[Optional[int], Snowflake] = commands.flag(default=None,
                                                               description="Search for messages after this message ID")
    user: Optional[discord.Member] = commands.flag(default=None, description="Remove messages from the specified user")
    bots: Optional[bool] = commands.flag(default=None, description="Removes messages from bots")
