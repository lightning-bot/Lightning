import aiohttp
import discord
from discord.ext import commands
# import io
# from PIL import Image, ImageFilter
import random


class Fun(commands.Cog):
    """Fun Stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.bot.log.info(f'{self.qualified_name} loaded')

   # async def get_image(self, ctx, url)

    #def final_image(self, image): # Image Sav
    #    image_file = io.BytesIO()
    #    image.save(image_file, format="png")
    #    image_file.seek(0)
    #    return image_file


    @commands.command(name="8ball")
    @commands.cooldown(rate=1, per=4.0, type=commands.BucketType.channel)
    async def eight_ball(self, ctx, *, question: commands.clean_content):
        """Ask 8ball a question"""
        response = ["no", "most certainly", "doubtful", "it is certain", "ask again", "maybe", "🤷"]
        await ctx.send(f"{ctx.author.mention} You asked: `{question}`. | 8ball says {random.choice(response)}")


    @commands.command()
    async def cat(self, ctx):
        """Random Cat Pics from random.cat"""
        async with self.session.get('http://aws.random.cat/meow') as resp:
            data = await resp.json()
        embed = discord.Embed(title="Meow <:meowawauu:559383939513581569>", color=discord.Color.teal())
        embed.set_image(url=data['file'])
        embed.set_footer(text="Powered by random.cat", icon_url="https://purr.objects-us-east-1.dream.io/static/ico/favicon-96x96.png")
        await ctx.send(embed=embed)

    @commands.command()
    async def dog(self, ctx):
        """Random dog pics from dog.ceo"""
        async with self.session.get('https://dog.ceo/api/breeds/image/random') as resp:
            data = await resp.json()
        embed = discord.Embed(title="Bark 🐶", color=discord.Color.blurple())
        embed.set_image(url=data['message'])
        embed.set_footer(text="Powered by dog.ceo", icon_url="https://dog.ceo/img/favicon.png")
        await ctx.send(embed=embed)

    @commands.command()
    async def lenny(self, ctx):
        """( ͡° ͜ʖ ͡°)"""
        await ctx.send("( ͡° ͜ʖ ͡°)")



def setup(bot):
    bot.add_cog(Fun(bot))