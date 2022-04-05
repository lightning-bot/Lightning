"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
from __future__ import annotations

import contextlib
import re
from typing import Union

from discord.ext import commands

from lightning.converters import ReadableTextChannel, ReadableThread
from lightning.errors import LightningError


class ReadableChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = None

        with contextlib.suppress(commands.BadUnionArgument):
            channel = await commands.run_converters(ctx, Union[ReadableTextChannel, ReadableThread], argument,
                                                    ctx.current_parameter)

        if not channel:
            raise commands.BadArgument(f"Unable to convert \"{argument}\" to a channel or thread")
        return channel


class Message(commands.Converter):
    async def convert(self, ctx, argument):
        if len(argument) == 2:
            try:
                message = int(argument[0])
            except ValueError:
                raise LightningError("Not a valid message ID.")
            channel = await ReadableChannel().convert(ctx, argument[1])
            return message, channel
        # regex from d.py
        argument = argument[0]
        link_regex = re.compile(
            r'^https?://(?:(ptb|canary)\.)?discord(?:app)?\.com/channels/'
            r'(?:([0-9]{15,21})|(@me))'
            r'/(?P<channel_id>[0-9]{15,21})/(?P<message_id>[0-9]{15,21})/?$'
        )
        match = link_regex.match(argument)
        if not match:
            # Same message from channel...
            try:
                message = int(argument)
            except ValueError:
                raise LightningError("Not a valid message ID.")
            channel = ctx.channel
            return message, channel
        message_id = int(match.group("message_id"))
        channel_id = match.group("channel_id")
        channel = await ReadableChannel().convert(ctx, channel_id)
        return message_id, channel
