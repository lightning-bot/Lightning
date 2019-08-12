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

class Memes(commands.Cog):
    def __init__(self, bot):
        """Approved™ memes"""
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    async def listmemes(self, ctx):
        """Lists meme commands"""
        embed = discord.Embed(description="\n")
        embed.description += ", ".join([x.name for x in self.get_commands() if x != self.listmemes])
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def astar(self, ctx):
        """Here's a star just for you."""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/vUrBPZr.png")

    @commands.command(hidden=True, aliases=['inori'])
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def hifumi1(self, ctx):
        """Disappointment"""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/jTTHQLs.gifv")

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def thisisgit(self, ctx):
        """Git in a nutshell"""
        await ctx.send(f"{ctx.author.display_name}: https://gitlab.com/LightSage/bunches-of-images/raw/master/lightning/xkcd.png") # Using the img hosted on Gitlab for now   

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def knuckles(self, ctx):
        # It's just as bad
        re_list = ['to frii gaems', 'to bricc', 'to get frii gaems', 'to build sxos',
                   'to play backup games', 'to get unban', 'to get reinx games',
                   'to build atmos', 'to brick my 3ds bc ebay scammed me', 'to plz help me'] 
        whenlifegetsatyou = ['?!?!?', '?!?!', '.', '!!!!', '!!', '!']
        await ctx.send(f"Do you know da wae {random.choice(re_list)}{random.choice(whenlifegetsatyou)}")

    @commands.command(name="neo-ban", aliases=['neoban'], hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def neoban(self, ctx, member: discord.Member=None):
        if member is None:
            member = ctx.author

        await ctx.send(f"{member.mention} is now neo-banned!")

    @commands.command(aliases=['discordcopypasta'], hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def discordcopypaste(self, ctx, member: discord.Member=None):
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

        await ctx.send(org_msg)

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def bean(self, ctx):
        """:fastbean:"""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/t1RFSL7.jpg")

    @commands.command(hidden=True)
    async def peng(self, ctx):
        """Uhhh ping?"""
        await ctx.send(f"My ping is uhhh `{random.randint(31,150)}ms`")
       
def setup(bot):
    bot.add_cog(Memes(bot))