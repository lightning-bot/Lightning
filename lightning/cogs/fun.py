"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
import io
import math
import random
import textwrap
import typing

import bottom
import discord
import slowo
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
        img = Image.open("resources/templates/kurisudraw.png")
        dafont = ImageFont.truetype(font="resources/fonts/Montserrat-Regular.ttf",
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
        img = Image.open("resources/templates/fyi.png")
        font = ImageFont.truetype(font="resources/fonts/Heebo-Regular.ttf",
                                  size=86, encoding="unic")
        draw = ImageDraw.Draw(img)
        text = textwrap.wrap(text, width=19)
        y_text = 200
        wdmax = 1150
        for line in text:
            if y_text >= 706:
                break
            line_width, line_height = draw.textsize(line, font=font)
            draw.multiline_text(((wdmax - line_width) / 2, y_text),
                                line, font=font,
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
        async with self.bot.aiosession.get(user.avatar.with_format("png").url) as resp:
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
        if member.id == 376012343777427457 or member.id == self.bot.user.id:
            return  # :mystery:

        async with ctx.typing():
            avy = await self.get_user_avatar(member)
            image_buffer = await self.make_circle_related_meme(avy, "resources/templates/inthehead.png", (64, 64),
                                                               (14, 43))
            await ctx.send(file=discord.File(image_buffer, "screwedupinthehead.png"))

    @command()
    @commands.cooldown(2, 60.0, commands.BucketType.guild)
    async def iq(self, ctx: LightningContext, member: discord.Member = commands.default.Author) -> None:
        """Your iq is 3"""
        if member.id == 376012343777427457 or member.id == self.bot.user.id:
            return  # :mystery:

        async with ctx.typing():
            avy = await self.get_user_avatar(member)
            image_buffer = await self.make_circle_related_meme(avy, "resources/templates/fujiwara-iq.png", (165, 165),
                                                               (140, 26))
            await ctx.send(file=discord.File(image_buffer, "huh_my_iq_is.png"))

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
    @commands.cooldown(rate=3, per=5, type=commands.BucketType.channel)
    async def owoify(self, ctx: LightningContext, **args) -> None:
        """Turns a message into owo-speak"""
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

        if not text:
            raise commands.BadArgument("Missing text to translate into owo")

        fmt = slowo.UwU.ify(text)
        await ctx.send(fmt)

    @flags.add_flag("--random", "-R", is_bool_flag=True,
                    help="Bottomifies random text from the last 20 messages in this channel")
    @flags.add_flag("--lastmessage", "--lm", is_bool_flag=True,
                    help="Bottomifies the last message sent in the channel")
    @flags.add_flag("--regress", "--decode", is_bool_flag=True,
                    help="Decodes instead of encodes")
    @command(cls=flags.FlagCommand, aliases=['bottom'], raise_bad_flag=False)
    @commands.cooldown(rate=3, per=5, type=commands.BucketType.channel)
    async def bottomify(self, ctx: LightningContext, *, flags):
        """Turns a message into bottom"""
        if flags.random is True and flags.lastmessage is True:
            raise commands.BadArgument("--lastmessage and --random cannot be mixed together.")

        if flags.random is True:
            message = await self.get_previous_messages(ctx, ctx.channel, 35)
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find any message content.')
        elif flags.lastmessage is True:
            messages = await self.get_previous_messages(ctx, ctx.channel, 1, False)
            message = messages[0]
            if message.content:
                text = message.content
            else:
                raise LightningError('Failed to find message content in the previous message.')
        else:
            text = flags.rest

        if not text:
            raise commands.BadArgument("Missing text to translate into bottom")

        if flags.regress:
            try:
                await ctx.send(bottom.decode(text))
            except ValueError:
                await ctx.send("Failed to decode message.")
        else:
            await ctx.send(bottom.encode(text))

    @command()
    async def lolice(self, ctx: LightningContext, *, user: discord.Member = commands.default.Author) -> None:
        """Lolice chief"""
        url = f'https://nekobot.xyz/api/imagegen?type=lolice&url={user.avatar.with_format("png")}'
        data = await ctx.request(url)
        embed = discord.Embed()
        embed.set_image(url=data['message'])
        await ctx.send(embed=embed)

    @command()
    async def awooify(self, ctx: LightningContext, *, user: discord.Member = commands.default.Author) -> None:
        """Awooify a user"""
        url = f'https://nekobot.xyz/api/imagegen?type=awooify&url={user.avatar.with_format("png")}'
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
        data = await ctx.request("https://dog.ceo/api/breeds/image/random")
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=data['message'])
        embed.set_footer(text="Powered by dog.ceo", icon_url="https://dog.ceo/img/favicon.png")
        await ctx.send(embed=embed)

    @flags.add_flag("--message", converter=discord.Message)
    @command(cls=flags.FlagCommand, rest_attribute_name="text")
    async def mock(self, ctx: LightningContext, **args) -> None:
        """Mocks text"""
        if args['message']:
            text = args['message'].content
            if not text:
                raise commands.BadArgument("No message content was found in that message.")
        else:
            text = args['text']

        if not text:
            raise commands.BadArgument("Missing text to mock")

        m = [random.choice([char.upper(), char.lower()]) for char in text]
        await ctx.send("".join(m))


def setup(bot: LightningBot) -> None:
    bot.add_cog(Fun(bot))
