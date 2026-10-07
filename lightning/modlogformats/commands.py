"""
Lightning.py - A Discord bot
Copyright (C) 2019-present Célveren

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

import discord

from lightning.events import CommandEvent
from lightning.formatters import base_user_format
from lightning.modlogformats.base import FormatContext, Renderer, renders
from lightning.modlogformats.member import format_user


@renders(CommandEvent)
class CommandRan(Renderer[CommandEvent]):
    def mentions(self):
        return [self.event.user]

    def emoji(self) -> str:
        event = self.event
        return f"\N{CLIPBOARD} **Command Used**: {event.user.mention} ran `{event.command}`\n"\
               f"__Channel__: {event.channel.mention} | {event.channel.name}"

    def minimal(self, ctx: FormatContext) -> str:
        event = self.event
        return f"{self.stamp(ctx, event.ran_at)}**Command Ran**\n**Command**: {event.command}\n"\
               f"**User**: {format_user(event.user)}\n**Channel**: {base_user_format(event.channel)}"

    def embed(self) -> discord.Embed:
        event = self.event
        embed = discord.Embed(title="Command Ran", color=0xf74b06, timestamp=event.ran_at)
        embed.description = f"**Command**: {event.command}\n**User**: {event.user.mention} ({event.user.id})"\
                            f"\n**Channel**: {event.channel.mention} ({event.channel.id})"
        return embed
