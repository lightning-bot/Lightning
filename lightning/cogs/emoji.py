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
import asyncio
import io
import logging
import re
import unicodedata

import discord
from discord.ext import commands

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, command, errors, group)
from lightning.converters import EmojiRE, Whitelisted_URL
from lightning.utils.checks import has_guild_permissions
from lightning.utils.modlogformats import action_format

log = logging.getLogger(__name__)


class Emoji(LightningCog):
    """Emoji related commands"""
    @group(aliases=['emote'], invoke_without_command=True)
    async def emoji(self, ctx: LightningContext) -> None:
        """Emoji management commands"""
        await ctx.send_help("emoji")

    @emoji.command(aliases=['copy'], level=CommandLevel.Admin)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @has_guild_permissions(manage_emojis=True)
    async def add(self, ctx: GuildContext, *args) -> None:
        """Adds an emoji to the server"""
        error_msg = "Expected a custom emote. To add an emoji with a link, you must provide the name and url"\
                    " like <name> <url>."
        if len(args) == 1:
            regexmatch = re.match(r"<(a?):([A-Za-z0-9_]+):([0-9]+)>", args[0])
            if not regexmatch:
                raise errors.EmojiError("That's not a custom emoji \N{THINKING FACE}")
            try:
                emoji = await commands.PartialEmojiConverter().convert(ctx, args[0])
            except commands.BadArgument:
                raise commands.BadArgument(error_msg)
            emoji_name = emoji.name
            url = str(emoji.url)
        elif len(args) == 2:
            url = args[1]
            emoji_name = args[0]
        elif len(args) >= 3 or len(args) == 0:
            raise commands.BadArgument(error_msg)

        wurl = Whitelisted_URL(url)
        if len(emoji_name) > 32:
            await ctx.send("Emoji name cannot be longer than 32 characters!")
            return

        emoji_link = await ctx.request(str(wurl))
        _bytes = io.BytesIO()
        _bytes.write(emoji_link)
        _bytes.seek(0)

        try:
            coro = ctx.guild.create_custom_emoji(name=emoji_name, image=_bytes.read(),
                                                 reason=action_format(ctx.author, "Emoji added by"))
            emoji = await asyncio.wait_for(coro, timeout=15.0)
        except asyncio.TimeoutError:
            await ctx.send("The bot is ratelimited or creation took too long. Try again later.")
            return
        except discord.HTTPException as e:
            if e.code == 30008:
                await ctx.send("Unable to add that emoji because this server's emoji list is full.")
                return
            elif e.code == 50035:
                await ctx.send("Image is too big to upload. Emojis cannot be larger than 256kb")
                return

            log.debug(f"Tried to upload {str(wurl)} but failed with {e}")
            raise
        else:
            await ctx.send(f"Successfully created {emoji} `{emoji}`")

    @emoji.command()
    async def info(self, ctx: LightningContext, emote: discord.Emoji = commands.param(converter=EmojiRE)) -> None:
        """Gives some info on an emote.

        For unicode emoji: use `charinfo`"""
        embed = discord.Embed(title=emote.name, color=0xFFFF00)
        embed.description = f"[Emoji Link]({emote.url})"
        embed.add_field(name="ID", value=emote.id)
        embed.set_thumbnail(url=emote.url)

        managed = getattr(emote, 'managed', None)
        created = getattr(emote, 'created_at', None)
        if managed:
            embed.description += ("\n\nThis emoji is managed by a Twitch integration")
        if created:
            embed.set_footer(text="Emoji created at")
            embed.timestamp = created

        await ctx.send(embed=embed)

    @info.error
    async def emoji_error(self, ctx: LightningContext, error) -> None:
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(error)

    @command()
    async def charinfo(self, ctx: LightningContext, *, characters: str) -> None:
        """Shows information for a character"""
        def repr_unicode(c):
            name = unicodedata.name(c, 'Name not found.')
            return f'`{name}` - {c} \N{EM DASH} <http://www.fileformat.info/info/unicode/char/{ord(c):x}>'

        content = '\n'.join(map(repr_unicode, characters))
        if len(content) > 2000:
            await ctx.send('Output too long to display.')
            return
        await ctx.send(content)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Emoji(bot))
