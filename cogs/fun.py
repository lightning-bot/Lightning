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

import aiohttp
import discord
from discord.ext import commands
import io
from PIL import Image, ImageDraw, ImageFont
import random
import math
import config
from datetime import datetime
import textwrap
from utils.errors import NoImageProvided
from jishaku.functools import executor_function
from bolt.http import getbytes, getjson


class Fun(commands.Cog):
    """Fun Stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def c_to_f(self, c):
        """stolen from Robocop-ng. """
        return math.floor(9.0 / 5.0 * c + 32)

    def make_kcdt(self, text: str):
        img = Image.open("resources/templates/kurisudrawtemp.png")
        dafont = ImageFont.truetype(font="resources/fonts/arialrounded.ttf",
                                    size=42, encoding="unic")
        draw = ImageDraw.Draw(img)
        # Shoutouts to that person on stackoverflow that I don't remember
        y_text = 228
        wdmax = 560
        lines = textwrap.wrap(text, width=20)
        for line in lines:
            if y_text >= 390:
                break
            line_width, line_height = draw.textsize(line, font=dafont)
            draw.multiline_text(((wdmax - line_width) / 2, y_text),
                                line, font=dafont,
                                fill="black")  # align="center")
            y_text += line_height
        finalbuffer = io.BytesIO()
        img.save(finalbuffer, 'png')
        finalbuffer.seek(0)
        return finalbuffer

    def make_jpegify(self, url):
        img = Image.open(io.BytesIO(url))

        buff = io.BytesIO()
        img.convert("RGB").save(buff, "jpeg",
                                quality=random.randrange(1, 15))
        buff.seek(0)

        return buff

    @commands.command(aliases=['kurisudraw'])
    @commands.has_permissions(attach_files=True)
    async def kurisuwhiteboard(self, ctx, *, text: str):
        """Kurisu can solve this, can you?"""
        async with ctx.typing():
            img_buff = await ctx.bot.loop.run_in_executor(None,
                                                          self.make_kcdt,
                                                          text)
            await ctx.send(file=discord.File(img_buff, filename="kurisudraw.png"))

    @commands.command()
    @commands.has_permissions(attach_files=True)
    async def jpegify(self, ctx, url: str = None):
        """Jpegify's an image"""
        async with ctx.typing():
            if url is None:
                raise NoImageProvided
            if url:
                image_url = await getbytes(self.bot.aiosession, url)
                image_buffer = await ctx.bot.loop.run_in_executor(None,
                                                                  self.make_jpegify,
                                                                  image_url)
                await ctx.send(file=discord.File(image_buffer, filename="jpegify.jpeg"))
            else:
                raise NoImageProvided

    @executor_function
    def make_lakitu(self, text: str):
        img = Image.open("resources/templates/lakitutemp.png")
        verdana = ImageFont.truetype(font="resources/fonts/verdana.ttf",
                                     size=86, encoding="unic")
        draw = ImageDraw.Draw(img)
        text = textwrap.wrap(text, width=19)
        y_text = 200
        wdmax = 1150
        for line in text:
            if y_text >= 706:
                break
            line_width, line_height = draw.textsize(line, font=verdana)
            draw.multiline_text(((wdmax - line_width) / 2, y_text),
                                line, font=verdana,
                                fill="black")  # align="center")
            y_text += line_height
        finalbuffer = io.BytesIO()
        img.save(finalbuffer, 'png')
        finalbuffer.seek(0)
        return finalbuffer

    @commands.command()
    @commands.has_permissions(attach_files=True)
    async def lakitufyi(self, ctx, *, text: str):
        """Makes a Lakitu FYI meme with your own text"""
        async with ctx.typing():
            image_buffer = await self.make_lakitu(text)
            await ctx.send(file=discord.File(image_buffer, filename="fyi.png"))

    @commands.command(name="8ball")
    @commands.cooldown(rate=1, per=4.0, type=commands.BucketType.channel)
    async def eight_ball(self, ctx, *, question: commands.clean_content):
        """Ask 8ball a question"""
        response = ["no", "most certainly", "doubtful", "it is certain", "ask again", "maybe", "🤷"]
        await ctx.send(f"{ctx.author.mention} You asked: `{question}`. | 8ball says {random.choice(response)}")

    @commands.command(aliases=['roll'])
    async def die(self, ctx, *, number: int):
        """Rolls a 1 to the specified number sided die"""
        if number <= 0:
            return await ctx.send("You can't roll that!")
        number_ran = random.randint(1, number)
        await ctx.send(f"🎲 You rolled a `{number}` sided die. | The die rolled on `{number_ran}`")

    @die.error
    async def dice_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send("You need to specify a number!")
        elif isinstance(error, commands.BadArgument):
            return await ctx.send(error)

    @commands.command()  # Technically more of a meme, but /shrug
    async def bam(self, ctx, target: discord.Member):
        """Bams a user"""
        safe_name = await commands.clean_content().convert(ctx, str(target))
        # :idontfeelsogood:
        random_bams = ["n̟̤͙̠̤̖ǫ̺̻ͅw̴͍͎̱̟ ̷̭̖̫͙̱̪b͏͈͇̬̠̥ͅ&̻̬.̶̜͍̬͇̬ ҉̜̪̘̞👍̡̫͙͚͕ͅͅ", "n͢ow̢ ͜b&͢. ̷👍̷",
                       "n҉̺o̧̖̱w̯̬̜̺̘̮̯ ͉͈͎̱̰͎͡b&̪̗̮̣̻͉.͍͖̪͕̤͔ ͢👍̵͙̯͍̫̬",
                       "ńo̶̡͜w͘͟͏ ҉̶b̧&̧.̡͝ ̕👍̡͟", "n҉o̢͘͞w̢͢ ̢͏̢b͠&̴̛.̵̶ ̢́👍̴",
                       "n̶̵̵̷̡̲̝̺o̵̶̷̴̜͚̥͓w̶̶̶̴͔̲͢͝ ḇ̶̷̶̵̡̨͜&̷̴̶̵̢̗̻͝.̷̵̴̶̮̫̰͆ 👍̵̶̵̶̡̡̹̹",
                       "n̸̶̵̵̷̴̷̵̷̒̊̽ò̷̷̷̶̶̶̶̴̝ͥ̄w̶̶̷̶̵̴̷̶̴̤̑ͨ b̷̵̶̵̶̷̵̴̶̧͌̓&̵̶̵̶̷̴̵̴̻̺̓̑.̵̴̷̵̶̶̶̷̷̹̓̉ 👍",
                       "no̥̊w ͜͠b̹̑&̛͕.̡̉ 👍̡̌",
                       "n̐̆ow͘ ̌̑b͛͗&͗̂̍̒.̄ ͊👍͂̿͘",
                       "ₙₒw b&. 👍", "n҉o҉w҉ b҉&. 👍"]

        await ctx.send(f"{safe_name} is {random.choice(random_bams)}")

    @commands.command()  # Another meme
    async def warm(self, ctx, user: discord.Member):
        """Warms a user"""
        celsius = random.randint(15, 100)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} warmed. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command(aliases=['cool', 'cold'])  # Another meme again
    async def chill(self, ctx, user: discord.Member):
        """Chills/cools a user"""
        celsius = random.randint(-50, 15)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} chilled. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command()
    async def cryofreeze(self, ctx, user: discord.Member = None):
        """Cryofreezes a user"""
        if user is None:
            user = ctx.author
        celsius = random.randint(-100, 0)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user.mention} cryofreezed. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.group(aliases=['cade'])
    async def cat(self, ctx):
        """Random cats pics either from TheCatAPI or random.cat"""
        if ctx.invoked_subcommand is None:
            ranco = ["catapi", "randomcat"]
            listo = random.choice(ranco)
            await ctx.invoke(self.bot.get_command(f"cat {listo}"))

    @cat.command()
    async def randomcat(self, ctx):
        """Random Cat Pics from random.cat"""
        async with self.bot.aiosession.get('http://aws.random.cat/meow') as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                return await ctx.send(f"HTTP ERROR {resp.status}. Try again later(?)")
        embed = discord.Embed(title="Meow <:meowawauu:604760862049304608>",
                              color=discord.Color.teal())
        embed.set_image(url=data['file'])
        embed.set_footer(text="Powered by random.cat",
                         icon_url="https://purr.objects-us-east-1.dream.io/static/ico/favicon-96x96.png")
        await ctx.send(embed=embed)

    @cat.command(aliases=['capi'])
    async def catapi(self, ctx):
        """Random Cat Pics from thecatapi.com"""
        capi = {"x-api-key": config.catapi_token}
        session = aiohttp.ClientSession(headers=capi)
        async with session.get(url='https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status == 200:
                dat = await resp.json()
            else:
                return await ctx.send(f"HTTP ERROR {resp.status}. Try again later(?)")
        embed = discord.Embed(title="Meow <:meowawauu:604760862049304608>",
                              color=discord.Color(0x0c4189))
        for cat in dat:  # There's only one but shrug.avi
            embed.set_image(url=cat['url'])
        embed.set_footer(text="Powered by TheCatApi")
        await ctx.send(embed=embed)

    @commands.command()
    async def dog(self, ctx):
        """Random dog pics from dog.ceo"""
        async with self.bot.aiosession.get('https://dog.ceo/api/breeds/image/random') as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                return await ctx.send("Something went wrong "
                                      "fetching dog pics! Try again later.")
        embed = discord.Embed(title="Bark 🐶", color=discord.Color.blurple())
        embed.set_image(url=data['message'])
        embed.set_footer(text="Powered by dog.ceo", icon_url="https://dog.ceo/img/favicon.png")
        await ctx.send(embed=embed)

    @commands.command()
    async def xkcd(self, ctx, xkcd_number: int = None):
        """Returns an embed with information about the specified xkcd comic.

        If no value is supplied or the value isn't found, it gives the latest xkcd instead."""
        xkcd_latest = await getjson(self.bot.aiosession, "https://xkcd.com/info.0.json")
        xkcd_max = xkcd_latest.get("num")

        if xkcd_number is not None and int(xkcd_number) > 0 and int(xkcd_number) < xkcd_max:
            entry = int(xkcd_number)
        else:
            entry = xkcd_max

        xkcd = await getjson(self.bot.aiosession, f"https://xkcd.com/{entry}/info.0.json")
        if xkcd is False:
            return await ctx.send("Something went wrong grabbing that XKCD!")

        timestamp = datetime.strptime(f"{xkcd['year']}-{xkcd['month']}-{xkcd['day']}",
                                      "%Y-%m-%d")
        embed = discord.Embed(title=f"xkcd {xkcd['num']}: {xkcd['safe_title']}",
                              url=f"https://xkcd.com/{xkcd['num']}",
                              timestamp=timestamp, color=discord.Color(0x96A8C8))
        embed.set_image(url=xkcd["img"])
        embed.set_footer(text=xkcd["alt"])
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Fun(bot))
