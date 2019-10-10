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

import discord
from discord.ext import commands
import random
import json


class Memes(commands.Cog):
    def __init__(self, bot):
        """Approved™ memes"""
        self.bot = bot
        self.memes_list = json.load(open('resources/memes.json',
                                         'r', encoding='utf8'))

    @commands.group(aliases=['meme'])
    async def memes(self, ctx):
        """Runs a meme command.

        If no meme is given, it sends a list of memes"""
        if ctx.invoked_subcommand is None:
            memeslist = "Text: `knuckles` `neo-ban` `discordcopypaste` `peng`"\
                        " `ayy` `lenny` `lmao` `r11`"\
                        "\nImage: `astar` `hifumi1` `git` `bean` `tuturu` `yert`"\
                        " `bait` `cat` `catto`"
            return await ctx.send(f"Available Memes:\n{memeslist}")

    @memes.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def astar(self, ctx):
        """Here's a star just for you."""
        await ctx.safe_send(f"{ctx.author.display_name}: https://i.imgur.com/vUrBPZr.png")

    @memes.command(hidden=True, aliases=['inori'])
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def hifumi1(self, ctx):
        """Disappointment"""
        await ctx.safe_send(f"{ctx.author.display_name}: https://i.imgur.com/jTTHQLs.gifv")

    @memes.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def git(self, ctx):
        """Git in a nutshell"""
        await ctx.safe_send(f"{ctx.author.display_name}: https://i.imgur.com/SyuscgW.png")

    @memes.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def knuckles(self, ctx):
        # It's just as bad
        re_list = ['to frii gaems', 'to bricc', 'to get frii gaems', 'to build sxos',
                   'to play backup games', 'to get unban', 'to get reinx games',
                   'to build atmos', 'to brick my 3ds bc ebay scammed me', 'to plz help me']
        whenlifegetsatyou = ['?!?!?', '?!?!', '.', '!!!!', '!!', '!']
        await ctx.send(f"Do you know da wae {random.choice(re_list)}{random.choice(whenlifegetsatyou)}")

    @memes.command(name="neo-ban", aliases=['neoban'], hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def neoban(self, ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author

        await ctx.send(f"{member.mention} is now neo-banned!")

    @memes.command(aliases=['discordcopypasta'], hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def discordcopypaste(self, ctx, member: discord.Member = None):
        """Generates a discord copypaste

        If no arguments are passed, it uses the author of the command.

        If you fall for this, you should give yourself a solid facepalm."""
        if member is None:
            member = ctx.author
        org_msg = f"Look out for a Discord user by the name of \"{member.name}\" with"\
                  f" the tag #{member.discriminator}. "\
                  "He is going around sending friend requests to random Discord users,"\
                  " and those who accept his friend requests will have their accounts "\
                  "DDoSed and their groups exposed with the members inside it "\
                  "becoming a victim aswell. Spread the word and send "\
                  "this to as many discord servers as you can. "\
                  "If you see this user, DO NOT accept his friend "\
                  "request and immediately block him. Our team is "\
                  "currently working very hard to remove this user from our database,"\
                  " please stay safe."

        await ctx.safe_send(org_msg)

    @memes.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def bean(self, ctx):
        """:fastbean:"""
        await ctx.safe_send(f"{ctx.author.display_name}: https://i.imgur.com/t1RFSL7.jpg")

    @memes.command(hidden=True)
    async def peng(self, ctx):
        """Uhhh ping?"""
        await ctx.safe_send(f"My ping is uhhh `{random.randint(31,150)}ms`")

    @memes.command(hidden=True)
    async def tuturu(self, ctx):
        """tuturu!"""
        await ctx.safe_send(f'{ctx.author.display_name}: '
                            'https://cdn.discordapp.com/emojis/562686801043521575.png?v=1')

    @memes.command(hidden=True)
    @commands.has_permissions(add_reactions=True)
    async def yert(self, ctx):
        await ctx.message.add_reaction("<:yert:623369666869461003>")
        await ctx.safe_send(f'{ctx.author.display_name}: '
                            'https://i.imgur.com/lsXvvdb.png')

    @memes.command(hidden=True)
    async def ayy(self, ctx):
        await ctx.send("Lmao")

    @memes.command(hidden=True)
    async def lenny(self, ctx):
        await ctx.send("( ͡° ͜ʖ ͡°)")

    @memes.command(hidden=True)
    async def lmao(self, ctx):
        await ctx.send("😂😂😂 Sorry, what were we laughing about again? 😂😂😂")

    @memes.command(name="bait", hidden=True)
    async def memes_bait(self, ctx):
        link = random.choice(self.memes_list['bait'])
        await ctx.safe_send(f'{ctx.author.display_name}: {str(link)}')

    @memes.command(name="cat", hidden=True)
    async def memes_cat(self, ctx):
        await ctx.safe_send(f'{ctx.author.display_name}: https://i.imgur.com/dCXyOfK.png')

    @memes.command(hidden=True)
    async def catto(self, ctx):
        """polite catto"""
        embed = discord.Embed(title=f"{ctx.author} says hello", color=discord.Color.blurple())
        embed.set_image(url="https://i.imgur.com/1nQSMLM.png")
        embed.set_footer(text="powered by cattos love", icon_url="https://i.imgur.com/1nQSMLM.png")
        await ctx.send(embed=embed)

    @memes.command(hidden=True)
    async def r11(self, ctx, member: discord.Member = None):
        """da most iMPORTANT rool"""
        if member is None:
            member = ctx.author
        piracyRule = f"da piracy rool."\
                     f"doont downlod games youo did note dump, {member.mention} or you are break rule!!1"\
                     f"dont ask hou to get frii game or u are loser {member.mention}"\
                     f"dont menshon pirate maps or {member.mention} is pirat"\
                     "don brek law"
        await ctx.send(piracyRule)


def setup(bot):
    bot.add_cog(Memes(bot))
