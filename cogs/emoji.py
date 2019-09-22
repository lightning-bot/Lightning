# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

from discord.ext import commands
import discord
import io
from discord.ext.commands import Cog
from utils.checks import is_one_of_guilds, is_staff_or_has_perms
from utils.paginators_jsk import paginator_reg_nops
import random

ROO_EMOTES = [604331487583535124, 604446987844190228, 606517600167526498, 610921560068456448]


class Emoji(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def aiobytesfinalize(self, image):
        file_e = io.BytesIO()
        file_e.write(image)
        file_e.seek(0)
        return file_e.read()

    @commands.command(aliases=['nemoji'])
    async def nitroemoji(self, ctx, emojiname):
        """Posts either an animated emoji or non-animated emoji if found"""
        emoji = discord.utils.get(self.bot.emojis, name=emojiname)
        if emoji:
            return await ctx.send(emoji)
        emojiname = emojiname.lower()
        rand = list(filter(lambda m: emojiname in m.name.lower(), self.bot.emojis))
        if rand:
            em = random.choice(rand)
            await ctx.send(em)
        else:
            return await ctx.send("No Emote Found!")

    @commands.group(aliases=['emote'])
    async def emoji(self, ctx):
        """Emoji management commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @emoji.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @is_staff_or_has_perms("Helper", manage_emojis=True)
    async def add(self, ctx, emoji_name, *, url):
        """Adds the URL as an emoji to the guild

        In order to use this command, you must either have
        Manage Emojis permission or a role that
        is assigned as a Helper or above in the bot."""
        if len(emoji_name) > 32:
            return await ctx.send("Emoji name cannot be longer than 32 characters!")
        emoji_link = await self.bot.aiogetbytes(url)
        if emoji_link is not False:
            emoji_aio = self.aiobytesfinalize(emoji_link)
            try:
                finalized_e = await ctx.guild.create_custom_emoji(name=emoji_name, image=emoji_aio,
                                                                  reason=f"Emoji Added by {ctx.author} "
                                                                  f"(ID: {ctx.author.id})")
            except Exception as ex:
                self.bot.log.error(ex)
                return await ctx.send("Something went wrong creating that emoji. Make sure this guild"
                                      " emoji\'s list isn\'t full and that emoji is under 256kb.")
            else:
                await ctx.send(f"Successfully created {finalized_e} `{finalized_e}`")
        else:
            return await ctx.send("Something went wrong trying to fetch the url. Try again later(?)")

    @emoji.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @is_staff_or_has_perms("Helper", manage_emojis=True)
    async def copy(self, ctx, emoji: discord.PartialEmoji):
        """ "Copies" an emoji and adds it to the guild.

        In order to use this command, you must either have
        Manage Emojis permission or a role that
        is assigned as a Helper or above in the bot."""
        emoji_link = await self.bot.aiogetbytes(str(emoji.url))
        if emoji_link is not False:
            try:
                fe = await ctx.guild.create_custom_emoji(name=emoji.name, image=emoji_link,
                                                         reason=f"Emoji Added by {ctx.author} "
                                                         f"(ID: {ctx.author.id})")
            except Exception as ex:
                self.bot.log.error(ex)
                return await ctx.send("Something went wrong creating that emoji. Make sure this guild"
                                      " emoji\'s list isn\'t full and that emoji is under 256kb.")
            else:
                await ctx.send(f"Successfully created {fe} `{fe}`")
        else:
            return await ctx.send("Something went wrong trying to fetch the url. Try again later(?)")

    @emoji.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @is_staff_or_has_perms("Helper", manage_emojis=True)
    async def delete(self, ctx, emote: discord.Emoji):
        """Deletes an emoji from the guild

        In order to use this command, you must either have
        Manage Emojis permission or a role that
        is assigned as a Moderator or above in the bot."""
        if ctx.guild.id != emote.guild_id:
            return await ctx.send("This emoji isn't in this guild!")

        await emote.delete(reason=f"Emoji Removed by {ctx.author} (ID: {ctx.author.id})")
        await ctx.send("Emote is now deleted.")

    @emoji.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @is_staff_or_has_perms("Helper", manage_emojis=True)
    async def rename(self, ctx, name: str, emote_to_rename: discord.Emoji):
        """Renames an emoji from the guild

        In order to use this command, you must either have
        Manage Emojis permission or a role that
        is assigned as a Moderator or above in the bot."""
        if ctx.guild.id != emote_to_rename.guild_id:
            return await ctx.send("This emoji does not belong to this guild!")

        try:
            await emote_to_rename.edit(name=name,
                                       reason=f"Emoji Renamed by {ctx.author} "
                                              f"(ID: {ctx.author.id})")
        except discord.HTTPException as e:
            return await self.bot.create_error_ticket(ctx, "Error", e)

        await ctx.safe_send(f"Renamed {emote_to_rename} to {name}")

    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    @emoji.command(name='list', aliases=['all'])
    async def listemotes(self, ctx):
        """Sends a paginator with a fancy list of the server's emotes"""
        page = []
        for emoji in ctx.guild.emojis:
            page.append(f'{emoji} -- `{emoji}`')
        await paginator_reg_nops(self.bot, ctx, size=1000, page_list=page)

    @emoji.command(aliases=['stat', 'statistics'])
    @commands.guild_only()
    async def stats(self, ctx):
        """Gives stats on how much room is left for emotes"""
        static = 0
        animated = 0
        for x, y in enumerate(ctx.guild.emojis):
            if y.animated:
                animated += 1
            else:
                static += 1
        emojicalc = f"**Static Emojis:** {static}\n**Animated Emojis:** {animated}"\
                    f"\n**Total:** {len(ctx.guild.emojis)}\nThere are "\
                    f"**{ctx.guild.emoji_limit - static}** slots left for static emojis "\
                    f"and **{ctx.guild.emoji_limit - animated}** slots left for animated emojis."
        await ctx.send(emojicalc)

    @emoji.command()
    async def info(self, ctx, emote: discord.PartialEmoji):
        """Gives some info on an emote. Unicode emoji are not supported!"""
        embed = discord.Embed(title=f"Emoji Info for {emote.name}", color=discord.Color(0xFFFF00))
        if emote.is_custom_emoji():
            embed.description = f"[Emoji Link]({emote.url})"
            embed.add_field(name="ID", value=emote.id)
            embed.set_thumbnail(url=emote.url)
        await ctx.send(embed=embed)

    @commands.command()
    @is_one_of_guilds(ROO_EMOTES)
    @commands.has_permissions(administrator=True)
    async def listrooemojis(self, ctx):
        """Prints a fancy list of the Roo Server's emotes"""
        if len(ctx.guild.emojis) == 0:
            return await ctx.send("This server has no emotes!")

        paginator = commands.Paginator(suffix='', prefix='')
        for emoji in ctx.guild.emojis:
            paginator.add_line(f'{emoji} -- `{emoji}`')

        for page in paginator.pages:
            await ctx.send(page)

    @Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if guild.id not in ROO_EMOTES:
            return
        if guild.id == ROO_EMOTES[0]:
            emoji_chan = self.bot.get_channel(604331488049365042)
            rm_emoji = [f"{emoji} -- `{emoji.id}`" for emoji in before if emoji not in after]
            mk_emoji = [f"{emoji} -- `{emoji}`" for emoji in after if emoji not in before]
            if len(rm_emoji) != 0:
                msg = "⚠ Emoji Removed: "
                msg += ", ".join(rm_emoji)
                await emoji_chan.send(msg)
            if len(mk_emoji) != 0:
                msg = "✅ Emoji Added: "
                msg += ", ".join(mk_emoji)
                await emoji_chan.send(msg)
        elif guild.id == ROO_EMOTES[1]:
            emoji_chan = self.bot.get_channel(604447679635783690)
            rm_emoji = [f"{emoji} -- `{emoji.id}`" for emoji in before if emoji not in after]
            mk_emoji = [f"{emoji} -- `{emoji}`" for emoji in after if emoji not in before]
            if len(rm_emoji) != 0:
                msg = "⚠ Emoji Removed: "
                msg += ", ".join(rm_emoji)
                await emoji_chan.send(msg)
            if len(mk_emoji) != 0:
                msg = "✅ Emoji Added: "
                msg += ", ".join(mk_emoji)
                await emoji_chan.send(msg)
        elif guild.id == ROO_EMOTES[2]:
            emoji_chan = self.bot.get_channel(606517971430539276)
            rm_emoji = [f"{emoji} -- `{emoji.id}`" for emoji in before if emoji not in after]
            mk_emoji = [f"{emoji} -- `{emoji}`" for emoji in after if emoji not in before]
            if len(rm_emoji) != 0:
                msg = "⚠ Emoji Removed: "
                msg += ", ".join(rm_emoji)
                await emoji_chan.send(msg)
            if len(mk_emoji) != 0:
                msg = "✅ Emoji Added: "
                msg += ", ".join(mk_emoji)
                await emoji_chan.send(msg)
        elif guild.id == ROO_EMOTES[3]:
            emoji_chan = self.bot.get_channel(610921684727365652)
            rm_emoji = [f"{emoji} -- `{emoji.id}`" for emoji in before if emoji not in after]
            mk_emoji = [f"{emoji} -- `{emoji}`" for emoji in after if emoji not in before]
            if len(rm_emoji) != 0:
                msg = "⚠ Emoji Removed: "
                msg += ", ".join(rm_emoji)
                await emoji_chan.send(msg)
            if len(mk_emoji) != 0:
                msg = "✅ Emoji Added: "
                msg += ", ".join(mk_emoji)
                await emoji_chan.send(msg)


def setup(bot):
    bot.add_cog(Emoji(bot))
