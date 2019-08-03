from discord.ext import commands
import discord
import io
import db.mod_check
from discord.ext.commands import Cog

ROO_EMOTES = [604331487583535124, 604446987844190228, 606517600167526498]

class Emoji(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

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
            await ctx.send(emoji)
        else:
            return await ctx.send("No Emote Found!")

    @commands.group()
    async def emoji(self, ctx):
        """Emoji management commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @emoji.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis=True)
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def add(self, ctx, emoji_name, *, url):
        """Adds the URL as an emoji to the guild
        
        Helpers+"""
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
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def copy(self, ctx, emoji: discord.PartialEmoji):
        """ "Copies" an emoji and adds it to the guild.
        
        Helpers+"""
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
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def delete(self, ctx, emote: discord.Emoji):
        """Deletes an emoji from the guild
        
        Moderators+"""
        if ctx.guild.id != emote.guild_id:
            return await ctx.send("This emoji isn't in this guild!")

        await emote.delete(reason=f"Emoji Removed by {ctx.author} (ID: {ctx.author.id})")
        await ctx.send("Emote is now deleted.")

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
        if guild.id == ROO_EMOTES[1]:
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
        if guild.id == ROO_EMOTES[2]:
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


def setup(bot):
    bot.add_cog(Emoji(bot))