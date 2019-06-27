import aiohttp
import discord
from discord.ext import commands
# import io
# from PIL import Image, ImageFilter
import random
import math


class Fun(commands.Cog):
    """Fun Stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.bot.log.info(f'{self.qualified_name} loaded')

    def c_to_f(self, c):
        """stolen from Robocop-ng. """
        return math.floor(9.0 / 5.0 * c + 32)

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

    @commands.command(aliases=['roll'])
    async def die(self, ctx, *, number: int):
        """Rolls a 1 to the specified number sided die"""
        if number == 0:
            return await ctx.send("You can't roll that!")
        number_ran = random.randint(1, number)
        await ctx.send(f"🎲 You rolled a `{number}` sided die. | The die rolled on `{number_ran}`")

    @die.error
    async def dice_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send("You need to specify a number!")

    @commands.command() # Technically more of a meme, but /shrug
    async def bam(self, ctx, target: discord.Member):
        """Bams a user"""
        safe_name = await commands.clean_content().convert(ctx, str(target))
        # :idontfeelsogood:
        random_bams = ["n̟̤͙̠̤̖ǫ̺̻ͅw̴͍͎̱̟ ̷̭̖̫͙̱̪b͏͈͇̬̠̥ͅ&̻̬.̶̜͍̬͇̬ ҉̜̪̘̞👍̡̫͙͚͕ͅͅ", "n͢ow̢ ͜b&͢. ̷👍̷", "n҉̺o̧̖̱w̯̬̜̺̘̮̯ ͉͈͎̱̰͎͡b&̪̗̮̣̻͉.͍͖̪͕̤͔ ͢👍̵͙̯͍̫̬", "ńo̶̡͜w͘͟͏ ҉̶b̧&̧.̡͝ ̕👍̡͟", "n҉o̢͘͞w̢͢ ̢͏̢b͠&̴̛.̵̶ ̢́👍̴", "n̶̵̵̷̡̲̝̺o̵̶̷̴̜͚̥͓w̶̶̶̴͔̲͢͝ ḇ̶̷̶̵̡̨͜&̷̴̶̵̢̗̻͝.̷̵̴̶̮̫̰͆ 👍̵̶̵̶̡̡̹̹",
        "n̸̶̵̵̷̴̷̵̷̒̊̽ò̷̷̷̶̶̶̶̴̝ͥ̄w̶̶̷̶̵̴̷̶̴̤̑ͨ b̷̵̶̵̶̷̵̴̶̧͌̓&̵̶̵̶̷̴̵̴̻̺̓̑.̵̴̷̵̶̶̶̷̷̹̓̉ 👍", "no̥̊w ͜͠b̹̑&̛͕.̡̉ 👍̡̌", "n̐̆ow͘ ̌̑b͛͗&͗̂̍̒.̄ ͊👍͂̿͘", "ₙₒw b&. 👍", "n҉o҉w҉ b҉&. 👍"]

        await ctx.send(f"{safe_name} is {random.choice(random_bams)}")

    @commands.command() # Another meme
    async def warm(self, ctx, user: discord.Member):
        """Warms a user"""
        celsius = random.randint(15, 100)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} warmed. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command(aliases=['cool', 'cold']) # Another meme again
    async def chill(self, ctx, user: discord.Member):
        """Chills/cools a user"""
        celsius = random.randint(-50, 15)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} chilled. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command()
    async def cryofreeze(self, ctx, user: discord.Member=None):
        """Cryofreezes a user"""
        if user is None:
            user = ctx.author
        celsius = random.randint(-100, 0)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} cryofreezed. User is now {celsius}°C ({fahrenheit}°F).")

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
