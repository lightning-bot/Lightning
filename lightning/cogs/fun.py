"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
import random
import typing

import bottom
import discord
import slowo
from discord.ext import commands
from jishaku.functools import executor_function
from PIL import Image

from lightning import (LightningBot, LightningCog, LightningContext, command,
                       converters, flags)
from lightning.errors import HTTPException, LightningError
from lightning.utils import helpers


async def LastImage(ctx: LightningContext):
    limit = 15
    async for message in ctx.channel.history(limit=limit):
        for embed in message.embeds:
            if embed.thumbnail and embed.thumbnail.url:
                return embed.thumbnail.url
        for attachment in message.attachments:
            if attachment.url:
                return attachment.url
    raise commands.BadArgument(f"Couldn't find an image in the last {limit} messages.")


class Fun(LightningCog):

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
    async def jpegify(self, ctx: LightningContext,
                      image: str = commands.parameter(default=LastImage,
                                                      displayed_default="<last image>")) -> None:
        """Jpegify an image"""
        async with ctx.typing():
            image = converters.Whitelisted_URL(image)
            byte_data = await ctx.request(image.url)
            image_buffer = await self.make_jpegify(byte_data)
            await ctx.send(file=discord.File(image_buffer, filename="jpegify.jpeg"))

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


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Fun(bot))
