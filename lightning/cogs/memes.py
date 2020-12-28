"""
Lightning.py - A multi-purpose Discord bot
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

import random

import discord
from discord.ext.commands import default

from lightning import (LightningBot, LightningCog, LightningCommand,
                       LightningContext, group)

BAIT = ["https://i.imgur.com/5VKDzO6.png",
        "https://i.imgur.com/28hcpAL.png",
        "https://i.imgur.com/bb2QhRT.png",
        "https://i.imgur.com/coTPufb.png",
        "https://i.imgur.com/AXnYOuW.png",
        "https://i.imgur.com/QcxVJGB.png",
        "https://i.imgur.com/yedHnzp.png",
        "https://i.imgur.com/j98dUfd.jpg",
        "https://i.imgur.com/UKiDbzb.png",
        "https://i.imgur.com/TJuk44x.jpg",
        "https://i.imgur.com/3jIgvE6.png",
        "https://i.imgur.com/sYxJqfg.png",
        "https://i.imgur.com/oz4rlRj.png",
        "https://garfield-is-a.lasagna.cat/i/5kx4.png",
        "https://i.imgur.com/QsL2mQM.png"]


class TextMeme(LightningCommand):
    def __init__(self, name, text, **kwargs):
        kwargs.update({"name": name})
        super().__init__(self._callback, **kwargs)
        self.text = text

        cog = kwargs.pop("cog", None)
        if self.cog is None and cog is not None:
            self.cog = cog

    async def _callback(self, cog, ctx: LightningContext) -> None:
        await ctx.send(str(self.text))


class TextMemeGroup(TextMeme):
    async def _callback(self, ctx: LightningContext) -> None:
        await ctx.send(str(self.text))


class Memes(LightningCog):
    """Approved™ memes"""

    def __init__(self, bot: LightningBot):
        self.bot = bot
        memes = self.bot.config._storage.get("memes", {})
        nongrouped = memes.get("non-grouped", {})
        nongroupedhidden = nongrouped.get("hidden", {})

        for key, value in memes.items():
            # I hate this
            if isinstance(value, dict):
                continue
            self.memes.add_command(TextMemeGroup(key, value))

        self.add_meme_commands(nongrouped, hidden=False)
        self.add_meme_commands(nongroupedhidden)

    def add_meme_commands(self, memes: dict, *, hidden=True):
        for key, value in memes.items():
            if isinstance(value, dict):
                continue
            self.bot.add_command(TextMeme(key, value, cog=self, hidden=hidden))

    @group(aliases=['meme'], invoke_without_command=True)
    async def memes(self, ctx: LightningContext) -> None:
        """Runs a meme command.

        If no meme is given, it sends a list of memes."""
        await ctx.send(f"Available Memes:\n{', '.join(x.name for x in self.memes.commands)}")

    @memes.command(aliases=['discordcopypasta'], hidden=True)
    async def discordcopypaste(self, ctx: LightningContext, member: discord.Member = default.Author) -> None:
        """Generates a discord copypaste

        If no arguments are passed, it uses the author of the command.

        If you fall for this, you should give yourself a solid facepalm."""
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

    @memes.command(name="bait", hidden=True)
    async def memes_bait(self, ctx: LightningContext) -> None:
        link = random.choice(BAIT)
        await ctx.send(str(link))

    @memes.command(hidden=True)
    async def catto(self, ctx: LightningContext) -> None:
        """polite catto"""
        embed = discord.Embed(title=f"{ctx.author} says hello", color=discord.Color.blurple())
        embed.set_image(url="https://i.imgur.com/1nQSMLM.png")
        embed.set_footer(text="powered by cattos love", icon_url="https://i.imgur.com/1nQSMLM.png")
        await ctx.send(embed=embed)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Memes(bot))
