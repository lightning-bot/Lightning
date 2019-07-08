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

    @commands.command(aliases=['discordcopypasta'])
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def discordcopypaste(self, ctx, member: discord.Member=None):
        """Generates a discord copypaste
        
        If no arguments are passed, it's uses the author of the command"""
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
       


def setup(bot):
    bot.add_cog(Memes(bot))
