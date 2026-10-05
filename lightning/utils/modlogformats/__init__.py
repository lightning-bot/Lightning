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
from lightning.utils.modlogformats.base import (BaseFormat, CompactModAction,
                                                action_format,
                                                base_user_format,
                                                construct_dm_message,
                                                escape_markdown_and_mentions,
                                                format_event, format_timestamp,
                                                log_actions, modlog_format,
                                                parse_format_setting)
# Importing these is what registers them with @modlog_format
from lightning.utils.modlogformats.embed import EmbedFormat
from lightning.utils.modlogformats.emoji import EmojiFormat
from lightning.utils.modlogformats.minimal import MinimalisticFormat

__all__ = (
    "BaseFormat", "CompactModAction", "EmbedFormat", "EmojiFormat", "MinimalisticFormat",
    "action_format", "base_user_format", "construct_dm_message", "escape_markdown_and_mentions",
    "format_event", "format_timestamp", "log_actions", "modlog_format", "parse_format_setting"
)
