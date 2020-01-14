# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
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

import colorsys
import io
import math
import random
import textwrap
import urllib
from datetime import datetime

import discord
from utils.http import getbytes, getjson
from discord.ext import commands
from jishaku.functools import executor_function
from PIL import Image, ImageDraw, ImageFont
from utils import flags

from utils.errors import NoImageProvided, LightningError


class Fun(commands.Cog):
    """Fun Stuff"""
    def __init__(self, bot):
        self.bot = bot

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
    async def die(self, ctx, number: int):
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

    # @commands.command()
    # @commands.bot_has_permissions(manage_messages=True)
    # async def ooftoggle(self, ctx):
    #    """Deletes messages that contain "oof" in them.
    # This isn't guaranteed to catch all instances of "oof"
    # and may misfire sometimes."""
    #    query = """INSERT INTO ooftoggle VALUES ($1, $2)"""

    @commands.command()  # Technically more of a meme, but /shrug
    async def bam(self, ctx, target: discord.Member):
        """Bams a user"""
        # :idontfeelsogood:
        random_bams = ["n̟̤͙̠̤̖ǫ̺̻ͅw̴͍͎̱̟ ̷̭̖̫͙̱̪b͏͈͇̬̠̥ͅ&̻̬.̶̜͍̬͇̬ ҉̜̪̘̞👍̡̫͙͚͕ͅͅ", "n͢ow̢ ͜b&͢. ̷👍̷",
                       "n҉̺o̧̖̱w̯̬̜̺̘̮̯ ͉͈͎̱̰͎͡b&̪̗̮̣̻͉.͍͖̪͕̤͔ ͢👍̵͙̯͍̫̬",
                       "ńo̶̡͜w͘͟͏ ҉̶b̧&̧.̡͝ ̕👍̡͟", "n҉o̢͘͞w̢͢ ̢͏̢b͠&̴̛.̵̶ ̢́👍̴",
                       "n̶̵̵̷̡̲̝̺o̵̶̷̴̜͚̥͓w̶̶̶̴͔̲͢͝ ḇ̶̷̶̵̡̨͜&̷̴̶̵̢̗̻͝.̷̵̴̶̮̫̰͆ 👍̵̶̵̶̡̡̹̹",
                       "n̸̶̵̵̷̴̷̵̷̒̊̽ò̷̷̷̶̶̶̶̴̝ͥ̄w̶̶̷̶̵̴̷̶̴̤̑ͨ b̷̵̶̵̶̷̵̴̶̧͌̓&̵̶̵̶̷̴̵̴̻̺̓̑.̵̴̷̵̶̶̶̷̷̹̓̉ 👍",
                       "no̥̊w ͜͠b̹̑&̛͕.̡̉ 👍̡̌",
                       "n̐̆ow͘ ̌̑b͛͗&͗̂̍̒.̄ ͊👍͂̿͘",
                       "ₙₒw b&. 👍", "n҉o҉w҉ b҉&. 👍"]

        await ctx.safe_send(f"{target} is {random.choice(random_bams)}")

    @commands.command()  # Another meme
    async def warm(self, ctx, user: discord.Member):
        """Warms a user"""
        celsius = random.randint(15, 100)
        fahrenheit = self.c_to_f(celsius)
        await ctx.safe_send(f"{user} warmed. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command(aliases=['cool', 'cold'])  # Another meme again
    async def chill(self, ctx, user: discord.Member):
        """Chills/cools a user"""
        celsius = random.randint(-50, 15)
        fahrenheit = self.c_to_f(celsius)
        await ctx.safe_send(f"{user} chilled. User is now {celsius}°C ({fahrenheit}°F).")

    @commands.command()
    async def cryofreeze(self, ctx, user: discord.Member = None):
        """Cryofreezes a user"""
        if user is None:
            user = ctx.author
        celsius = random.randint(-100, 0)
        fahrenheit = self.c_to_f(celsius)
        await ctx.safe_send(f"{user} cryofreezed. User is now {celsius}°C ({fahrenheit}°F).")

    async def get_previous_messages(self, channel):
        messages = await channel.history(limit=10).flatten()
        return random.choice(messages)

    @commands.command()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.channel)
    async def owoify(self, ctx, *, text: commands.clean_content()):
        """An owo-ifier.

        Flag options (no arguments):
        `--random`: Owoifies random text that was sent in the channel.
        `--lastmessage` or `--lm`: Owoifies the last message sent in the channel."""
        fwags = flags.boolean_flags(['--random', '--lastmessage'], text, False,
                                    {'--lm': '--lastmessage'})
        if fwags['--random'] is True:
            message = await self.get_previous_messages(ctx.channel)
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find any message content.')
        elif fwags['--lastmessage'] is True:
            messages = await ctx.channel.history(limit=2).flatten()
            message = messages[1]
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find message content'
                                     ' in the previous message.')
        else:
            text = fwags['text']
        url = f'https://nekos.life/api/v2/owoify?text={urllib.parse.quote(text)}'
        async with self.bot.aiosession.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                return await ctx.send(f"HTTP ERROR {resp.status}. Try again later(?)")
        await ctx.safe_send(data['owo'])

    @commands.command()
    async def lolice(self, ctx, *, user: discord.Member = None):
        """Lolice chief"""
        if not user:
            user = ctx.author
        url = f'https://nekobot.xyz/api/imagegen?type=lolice&url={user.avatar_url_as(format="png")}'
        async with self.bot.aiosession.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                return await ctx.send(f"HTTP ERROR {resp.status}. Try again later(?)")
        embed = discord.Embed()
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)

    @commands.command()
    async def awooify(self, ctx, *, user: discord.Member = None):
        """Awooify a user"""
        if not user:
            user = ctx.author
        url = f'https://nekobot.xyz/api/imagegen?type=awooify&url={user.avatar_url_as(format="png")}'
        async with self.bot.aiosession.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                return await ctx.send(f"HTTP ERROR {resp.status}. Try again later(?)")
        embed = discord.Embed()
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)

    @lolice.before_invoke
    @owoify.before_invoke
    @awooify.before_invoke
    async def do_typing_before(self, ctx):
        await ctx.trigger_typing()

    @commands.group(aliases=['cade'], invoke_without_command=True)
    async def cat(self, ctx):
        """Random cats pics either from TheCatAPI or random.cat"""
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
        capi = {"x-api-key": self.bot.config['tokens']['catapi']}
        async with self.bot.aiosession.get(url='https://api.thecatapi.com/v1/images/search', headers=capi) as resp:
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

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def headpat(self, ctx):
        """Random headpat gifs"""
        async with self.bot.aiosession.get("https://nekos.life/api/pat") as resp:
            headpat = await resp.json()
        url = headpat["url"]
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(title='Headpat, owo', colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=url)
        embed.set_footer(text="Powered by nekos.life", icon_url="https://nekos.life/static/icons/favicon-194x194.png")
        await ctx.send(embed=embed)

    @commands.command(name='slap')
    @commands.bot_has_permissions(embed_links=True)
    async def slap(self, ctx, person):
        """Slap yourself or someone."""
        async with self.bot.aiosession.get("https://nekos.life/api/v2/img/slap") as resp:
            slap = await resp.json()
        url = slap["url"]
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=url)
        embed.set_footer(text="Powered by nekos.life", icon_url="https://nekos.life/static/icons/favicon-194x194.png")
        try:
            person = await (commands.MemberConverter()).convert(ctx=ctx, argument=person)
        except commands.BadArgument:
            pass
        if isinstance(person, discord.Member) and person.id == ctx.author.id:
            embed.title = (f"*{ctx.author.name} slapped themself.*")
        else:
            if isinstance(person, discord.Member):
                name = person.name
            else:
                name = person[:30]
            embed.title = (f"*{ctx.author.name} slapped {name}*")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Fun(bot))
