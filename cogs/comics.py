import discord
from discord.ext import commands
from discord.ext.commands import Cog
import datetime
import aiohttp
from bs4 import BeautifulSoup
import io

class Comics(Cog):
    """Comics Cog"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command(aliases=['gc'])
    @commands.bot_has_permissions(embed_links=True)
    async def garfieldcomic(self, ctx, *, date=None):
        """Gets a comic by date posted. (Interactive)
        Example: 2012, 05, 12 would show the comic for December 05, 2012"""
        # This could be better, but it'll do for now
        def check(ms):
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author

        # base_url = "https://d1ejxu6vysztl5.cloudfront.net/comics/garfield/2014/2014-08-18.gif" # For Code Reference

        await ctx.send(content='What year would you like to pick?')

        msg = await self.bot.wait_for('message', check=check)
        year = msg.content # Set the Year

        await ctx.send(content='What month would you like to pick?')
        msg = await self.bot.wait_for('message', check=check)
        month = msg.content # Set the Month

        await ctx.send(content='What day would you like to pick?')
        msg = await self.bot.wait_for('message', check=check)
        day = msg.content # Set the Day


        returned_url = "https://d1ejxu6vysztl5.cloudfront.net/comics/garfield/" + str(year) + "/" + str(year) + "-" + str(month) + "-" + str(day) + ".gif"

        embed = discord.Embed()
        embed.title = "Your Requested Garfield Comic " + "(" + str(month) + "/" + str(day) + "/" + str(year) + ")"
        embed.set_image(url=returned_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['cgc'])
    @commands.bot_has_permissions(embed_links=True)
    async def currentgarfieldcomic(self, ctx):
        """Shows the current date's Garfield comic."""
        now = datetime.datetime.now()
        year = now.year
        month = now.strftime("%m")
        day = now.strftime("%d")

        today_comic = "https://d1ejxu6vysztl5.cloudfront.net/comics/garfield/" + str(year) + "/" + str(year) + "-" + str(month) + "-" + str(day) + ".gif"

        embed = discord.Embed(colour=discord.Colour(0xFF9900))
        embed.title = "Today's Garfield Comic " + "(" + str(month) + "/" + str(day) + "/" + str(year) + ")"
        embed.set_image(url=today_comic)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['rgc'])
    @commands.bot_has_permissions(embed_links=True)
    async def random_garfieldcomic(self, ctx):
        """Displays a random garfield comic
        
        Powered by GoComics"""
        url = "https://www.gocomics.com/random/garfield"
        async with self.session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class':'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random Garfield Comic", colour=discord.Colour(0xFF9900))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['ruac'])
    async def random_usacrescomic(self, ctx):
        """Displays a random US Acres comic
        
        Powered by GoComics"""
        url = "https://www.gocomics.com/random/us-acres"
        async with self.session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class':'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random U.S. Acres Comic", color=discord.Color(0xC3E4F7))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['rpc'])
    async def random_peanutscomic(self, ctx):
        """Displays a random Peanuts comic
        
        Powered by GoComics"""
        url = "https://www.gocomics.com/random/peanuts"
        async with self.session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class':'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random Peanuts Comic", color=discord.Color(0xFE0000))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['rgmgc'])
    async def random_garfieldminusgarfieldcomic(self, ctx):
        """Displays a random Garfield Minus Garfield comic
        
        Powered by GoComics"""
        url = "https://www.gocomics.com/random/garfieldminusgarfield"
        async with self.session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class':'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random Garfield Minus Garfield Comic", color=discord.Color(0xFF9900))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['rnsc'])
    async def random_nonsequiturcomic(self, ctx):
        """Displays a random Non Sequitur comic
        
        Powered by GoComics"""
        url = "https://www.gocomics.com/random/nonsequitur"
        async with self.session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class':'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random Non Sequitur Comic", color=discord.Color(0xE9F8FF))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)






def setup(bot):
    bot.add_cog(Comics(bot))