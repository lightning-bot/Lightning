"""
Lightning.py - A Discord bot
Copyright (C) 2019-2025 LightSage

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
import discord

from lightning.enums import LoggingType


def human_friendly_log_names(type: LoggingType):
    return type.to_simple_str().replace('|', ', ').replace('_', ' ').title()


def generate_message_embed(msg: discord.Message) -> discord.Embed:
    embed = discord.Embed(timestamp=msg.created_at)

    if hasattr(msg.author, 'nick') and msg.author.display_name != str(msg.author):
        author_name = f"{msg.author.display_name} ({msg.author})"
    else:
        author_name = msg.author

    embed.set_author(name=author_name, icon_url=msg.author.display_avatar.url)

    if msg.guild:
        embed.set_footer(text=f"\N{NUMBER SIGN}{msg.channel}")
    else:
        embed.set_footer(text=msg.channel)

    description = msg.content
    if msg.attachments:
        attach_urls = [
            f'[{attachment.filename}]({attachment.url})'
            for attachment in msg.attachments
        ]

        description += '\n\N{BULLET} ' + '\n\N{BULLET} '.join(attach_urls)
    if msg.embeds:
        description += "\n \N{BULLET} Message contains an embed(s)"
    embed.description = description

    return embed
