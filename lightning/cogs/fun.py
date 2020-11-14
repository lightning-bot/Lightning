"""
Lightning.py - A personal Discord bot
Copyright (C) 2020 - LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import colorsys
import io
import math
import random
import textwrap
import typing
from datetime import datetime

import discord
import uwuify
from discord.ext import commands
from jishaku.functools import executor_function
from PIL import Image, ImageDraw, ImageFont

from lightning import (LightningBot, LightningCog, LightningContext, command,
                       converters, flags)
from lightning.errors import HTTPException, LightningError
from lightning.utils import helpers


class Fun(LightningCog):

    def c_to_f(self, c) -> int:
        """stolen from Robocop-ng. """
        return math.floor(9.0 / 5.0 * c + 32)

    @executor_function
    def make_kcdt(self, text: str) -> io.BytesIO:
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

    @command(aliases=['kurisudraw'])
    @commands.cooldown(2, 60.0, commands.BucketType.guild)
    @commands.has_permissions(attach_files=True)
    async def kurisuwhiteboard(self, ctx: LightningContext, *, text: str) -> None:
        """Kurisu can solve this, can you?"""
        async with ctx.typing():
            img_buff = await self.make_kcdt(text)
            await ctx.send(file=discord.File(img_buff, filename="kurisudraw.png"))

    @executor_function
    def make_jpegify(self, _bytes: bytes) -> io.BytesIO:
        img = Image.open(io.BytesIO(_bytes))

        buff = io.BytesIO()
        img.convert("RGB").save(buff, "jpeg", quality=random.randrange(1, 10))
        buff.seek(0)

        return buff

    @command(aliases=['needsmorejpeg'])
    @commands.cooldown(3, 30.0, commands.BucketType.guild)
    @commands.has_permissions(attach_files=True)
    async def jpegify(self, ctx: LightningContext, image: str = converters.LastImage) -> None:
        """Jpegify an image"""
        async with ctx.typing():
            image = converters.Whitelisted_URL(image)
            byte_data = await helpers.request(image.url, self.bot.aiosession)
            image_buffer = await self.make_jpegify(byte_data)
            await ctx.send(file=discord.File(image_buffer, filename="jpegify.jpeg"))

    @executor_function
    def make_lakitu(self, text: str) -> io.BytesIO:
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

    @command()
    @commands.cooldown(2, 60.0, commands.BucketType.guild)
    @commands.has_permissions(attach_files=True)
    async def lakitufyi(self, ctx: LightningContext, *, text: str) -> None:
        """Makes a Lakitu FYI meme with your own text"""
        async with ctx.typing():
            image_buffer = await self.make_lakitu(text)
            await ctx.send(file=discord.File(image_buffer, filename="fyi.png"))

    async def get_user_avatar(self, user: typing.Union[discord.User, discord.Member]) -> bytes:
        async with self.bot.aiosession.get(str(user.avatar_url_as(format="png"))) as resp:
            avy_bytes = await resp.read()
        return avy_bytes

    @executor_function
    def make_circle_related_meme(self, avatar_bytes: bytes, path: str, resize_amount: tuple,
                                 paste: tuple) -> io.BytesIO:
        base_image = Image.open(path)
        avatar = Image.open(io.BytesIO(avatar_bytes)).resize(resize_amount).convert("RGB")

        mask = Image.new("L", avatar.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([(0, 0), avatar.size], fill=255)
        mask = mask.resize(resize_amount, Image.ANTIALIAS)

        base_image.paste(avatar, paste, mask=mask)

        buffer = io.BytesIO()
        base_image.save(buffer, "png")
        buffer.seek(0)

        return buffer

    @command()
    @commands.cooldown(2, 60.0, commands.BucketType.guild)
    async def screwedup(self, ctx: LightningContext, member: discord.Member = commands.default.Author) -> None:
        """Miko Iino tells you that you are screwed up in the head"""
        async with ctx.typing():
            avy = await self.get_user_avatar(member)
            image_buffer = await self.make_circle_related_meme(avy, "resources/templates/inthehead.png", (64, 64),
                                                               (14, 43))
            await ctx.send(file=discord.File(image_buffer, "screwedupinthehead.png"))

    @command()
    @commands.cooldown(2, 60.0, commands.BucketType.guild)
    async def iq(self, ctx: LightningContext, member: discord.Member = commands.default.Author) -> None:
        """Your iq is 3"""
        async with ctx.typing():
            avy = await self.get_user_avatar(member)
            image_buffer = await self.make_circle_related_meme(avy, "resources/templates/fujiwara-iq.png", (165, 165),
                                                               (140, 26))
            await ctx.send(file=discord.File(image_buffer, "huh_my_iq_is.png"))

    @command()
    async def bam(self, ctx: LightningContext, target: discord.Member) -> None:
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

        await ctx.send(f"{target} is {random.choice(random_bams)}")

    @command()
    async def warm(self, ctx: LightningContext, user: discord.Member) -> None:
        """Warms a user"""
        celsius = random.randint(15, 100)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user} warmed. User is now {celsius}°C ({fahrenheit}°F).")

    @command(aliases=['cool', 'cold'])
    async def chill(self, ctx: LightningContext, user: discord.Member) -> None:
        """Chills a user"""
        celsius = random.randint(-50, 15)
        fahrenheit = self.c_to_f(celsius)
        await ctx.send(f"{user} chilled. User is now {celsius}°C ({fahrenheit}°F).")

    async def get_previous_messages(self, ctx, channel, limit: int = 10,
                                    randomize=True) -> typing.Union[typing.List[discord.Message], discord.Message]:
        messages = await channel.history(limit=limit, before=ctx.message).flatten()
        if randomize:
            return random.choice(messages)
        else:
            return messages

    @flags.add_flag("--random", "-R", is_bool_flag=True,
                    help="Owoifies random text from the last 20 messages in this channel")
    @flags.add_flag("--lastmessage", "--lm", is_bool_flag=True,
                    help="Owoifies the last message sent in the channel")
    @command(cls=flags.FlagCommand, aliases=['owo', 'uwuify'], raise_bad_flag=False)
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.channel)
    async def owoify(self, ctx: LightningContext, **args) -> None:
        """An owo-ifier"""
        if args['random'] is True and args['lastmessage'] is True:
            raise commands.BadArgument("--lastmessage and --random cannot be mixed together.")

        if args['random'] is True:
            message = await self.get_previous_messages(ctx, ctx.channel, 20)
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find any message content.')
        elif args['lastmessage'] is True:
            messages = await self.get_previous_messages(ctx, ctx.channel, 1, False)
            message = messages[0]
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find message content in the previous message.')
        else:
            text = args['rest']

        uwutalk = uwuify.uwu(text, flags=(uwuify.SMILEY | uwuify.YU))
        await ctx.send(uwutalk)

    @command()
    async def lolice(self, ctx: LightningContext, *, user: discord.Member = commands.default.Author) -> None:
        """Lolice chief"""
        url = f'https://nekobot.xyz/api/imagegen?type=lolice&url={user.avatar_url_as(format="png")}'
        data = await ctx.request(url)
        embed = discord.Embed()
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)

    @command()
    async def awooify(self, ctx: LightningContext, *, user: discord.Member = commands.default.Author) -> None:
        """Awooify a user"""
        url = f'https://nekobot.xyz/api/imagegen?type=awooify&url={user.avatar_url_as(format="png")}'
        data = await ctx.request(url)
        embed = discord.Embed()
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)

    @lolice.before_invoke
    @owoify.before_invoke
    @awooify.before_invoke
    async def do_typing_before(self, ctx: LightningContext) -> None:
        await ctx.trigger_typing()

    @command(aliases=['cade'])
    async def cat(self, ctx: LightningContext) -> None:
        """Gives you a random cat picture"""
        try:
            data = await helpers.request("https://api.thecatapi.com/v1/images/search", self.bot.aiosession,
                                         headers={"x-api-key": self.bot.config['tokens']['catapi']})
        except HTTPException as e:
            await ctx.send(f"https://http.cat/{e.status}")
            return

        embed = discord.Embed(color=discord.Color(0x0c4189))
        embed.set_image(url=data[0]['url'])
        embed.set_footer(text="Powered by TheCatApi")
        await ctx.send(embed=embed)

    @command()
    async def dog(self, ctx: LightningContext) -> None:
        """Gives you a random dog picture"""
        data = await helpers.request("https://dog.ceo/api/breeds/image/random", self.bot.aiosession)
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=data['message'])
        embed.set_footer(text="Powered by dog.ceo", icon_url="https://dog.ceo/img/favicon.png")
        await ctx.send(embed=embed)

    @command()
    async def xkcd(self, ctx: LightningContext, value: int = None) -> None:
        """Shows an xkcd comic.

        If no value is supplied or the value isn't found, it gives the latest xkcd instead."""
        xkcd_latest = await helpers.request("https://xkcd.com/info.0.json", self.bot.aiosession)
        xkcd_max = xkcd_latest.get("num")

        if value is not None and int(value) > 0 and int(value) < xkcd_max:
            entry = int(value)
        else:
            entry = xkcd_max

        xkcd = await helpers.request(f"https://xkcd.com/{entry}/info.0.json", self.bot.aiosession)
        if xkcd is False:
            await ctx.send("Something went wrong grabbing that XKCD!")
            return

        timestamp = datetime.strptime(f"{xkcd['year']}-{xkcd['month']}-{xkcd['day']}",
                                      "%Y-%m-%d")
        embed = discord.Embed(title=f"xkcd {xkcd['num']}: {xkcd['safe_title']}",
                              url=f"https://xkcd.com/{xkcd['num']}",
                              timestamp=timestamp, color=discord.Color(0x96A8C8))
        embed.set_image(url=xkcd["img"])
        embed.set_footer(text=xkcd["alt"])
        await ctx.send(embed=embed)

    @command(aliases=['pat'])
    @commands.bot_has_permissions(embed_links=True)
    async def headpat(self, ctx: LightningContext) -> None:
        """Pat someone"""
        data = await helpers.request("https://nekos.life/api/pat", self.bot.aiosession)
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=data['url'])
        await ctx.send(embed=embed)

    @command()
    @commands.bot_has_permissions(embed_links=True)
    async def hug(self, ctx: LightningContext, *,
                  member: converters.WeebActionConverter("hugged") = None) -> None:  # noqa: F821
        """Hugs someone"""
        data = await ctx.request("https://nekos.life/api/v2/img/hug")
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(title=member, color=discord.Color.from_rgb(*color_random))
        embed.set_image(url=data['url'])
        await ctx.send(embed=embed)

    @command()
    @commands.bot_has_permissions(embed_links=True)
    async def slap(self, ctx: LightningContext, *,
                   person: converters.WeebActionConverter("slapped") = None) -> None:  # noqa: F821
        """Slap yourself or someone."""
        data = await ctx.request("https://nekos.life/api/v2/img/slap")
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(title=person, colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=data['url'])
        await ctx.send(embed=embed)

    @flags.add_flag("--message", converter=discord.Message)
    @command(cls=flags.FlagCommand)
    async def mock(self, ctx: LightningContext, **args) -> None:
        """Mocks text"""
        if args['message']:
            text = args['message'].content
            if not text:
                raise commands.BadArgument("No message content was found in that message.")
        else:
            text = args['rest']

        if not text:
            raise commands.BadArgument("Missing text to mock")

        m = [random.choice([char.upper(), char.lower()]) for char in text]
        await ctx.send("".join(m))


def setup(bot: LightningBot) -> None:
    bot.add_cog(Fun(bot))
