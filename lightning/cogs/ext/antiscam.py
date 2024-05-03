"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from __future__ import annotations

import re
from datetime import timedelta

import discord
import spacy
import spacy.tokens
from discord.ext import commands

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       group)
from lightning.utils.checks import is_server_manager

nlp = spacy.load("en_core_web_sm")
INVITE_REGEX = re.compile(r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?")
URL_REGEX = re.compile(r"https?:\/\/.*?$")
DOMAIN_REGEX = re.compile(r"(?:[A-z0-9](?:[A-z0-9-]{0,61}[A-z0-9])?\.)+[A-z0-9][A-z0-9-]{0,61}[A-z0-9]")
MASKED_LINKS = re.compile(r"\[[^\]]+\]\([^)]+\)")
MENTIONS_EVERYONE_REGEX = re.compile(r"(?P<here>\@here)|(?P<everyone>\@everyone)", flags=re.MULTILINE)


class AntiScamResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.mentions_everyone = False
        self.everyone_mention_count = 0
        self.here_mention_count = 0

        for match in MENTIONS_EVERYONE_REGEX.finditer(content):
            self.mentions_everyone = True
            if match.group("everyone"):
                self.everyone_mention_count += 1
            if match.group("here"):
                self.here_mention_count += 1

        self.author = None

    @classmethod
    def from_message(cls, message: discord.Message):
        cls = cls(message.content)
        cls.author = message.author
        return cls

    def identify_OF_spams(self, content: spacy.tokens.Doc, score: int):
        # The messages I've seen don't use masked links at all for OF spam, I could be wrong though
        for x, y in MASKED_LINKS.finditer(self.content):
            score -= 15

        if len(URL_REGEX.findall(self.content)) == 1:  # I have seen them only post 1 link
            score -= 20

        for token in content:
            if token.text in ("🍑", "🔞", "💦"):
                score -= 10
                continue

            if token.lemma_.lower() in ("leak", "teen"):
                score -= 5

        return score

    def identify_steam_scams(self, content: spacy.tokens.Doc, score: int):
        if MASKED_LINKS.search(self.content):
            score -= 30

        for token in content:
            if token.is_currency:
                for c in token.children:
                    if c.is_digit:
                        score -= 5
                score -= 10

            if token.is_ascii is False:
                score -= 5

        return score

    def calculate(self):
        content = nlp(self.content)
        score = 100
        if self.mentions_everyone:
            score -= 5

        if hasattr(self.author, "joined_at"):
            if self.author.joined_at >= discord.utils.utcnow() + timedelta(days=2):
                score -= 5

        # Go through named entities first
        for ent in content.ents:
            if ent.lemma_.lower in ("onlyfan", "onlyfans"):
                score -= 20
                return self.identify_OF_spams(content, score)

            if ent.lemma_.lower() == "steam":
                score -= 20
                return self.identify_steam_scams(content, score)

        nscore = 0
        for token in content:
            if token.lemma_.lower() in ("onlyfan", "onlyfans"):
                score -= 20
                return self.identify_OF_spams(content, score)

            if token.lemma_.lower() == "steam":
                score -= 20
                return self.identify_steam_scams(content, score)

            if token.lemma_.lower() == "nude":
                nscore += 5

        return score - nscore


class AntiScam(LightningCog):
    """An experimental anti-scam"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.active_guilds = set()

    async def cog_load(self):
        records = await self.bot.pool.fetch("SELECT guild_id FROM antiscam WHERE active='t';")
        for record in records:
            self.active_guilds.add(record['guild_id'])

    @LightningCog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return

        if message.guild.id not in self.active_guilds:
            return

        if message.author.bot:
            return

        if message.author.top_role >= message.guild.me.top_role:
            return

        res = AntiScamResult.from_message(message)
        score = res.calculate()
        if score < 60:
            try:
                await message.author.timeout(message.created_at + timedelta(hours=12),
                                             reason="AntiScam reported the message to be below the "
                                             f"safety rating ({score}%)")
                await message.delete()
            except discord.HTTPException:
                pass

    @group(level=CommandLevel.Admin)
    @is_server_manager()
    @commands.guild_only()
    async def antiscam(self, ctx: GuildContext):
        """
        Anti-scam is currently an experimental feature.
        It uses Natural Language Processing to determine a message's safety score.

        Anti-scam currently supports OnlyFans scams and Steam scams.
        Once enabled, this feature will scan every new message to see if it contains a scam.
        If the message's safety score reaches below 60%, the author of the message will be timed out for 12 hours.
        """
        ...

    @antiscam.command(name='enable', level=CommandLevel.Admin)
    @is_server_manager()
    @commands.guild_only()
    async def antiscam_enable(self, ctx: GuildContext):
        """Enables the experimental anti-scam"""
        query = """INSERT INTO antiscam (guild_id, active)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET active=EXCLUDED.active;"""
        await self.bot.pool.execute(query, ctx.guild.id, True)
        self.active_guilds.add(ctx.guild.id)
        await ctx.tick(True)

    @antiscam.command(name='disable', level=CommandLevel.Admin)
    @commands.guild_only()
    @is_server_manager()
    async def antiscam_disable(self, ctx: GuildContext):
        """Disables the experimental anti-scam"""
        query = """INSERT INTO antiscam (guild_id, active)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET active=EXCLUDED.active;"""
        await self.bot.pool.execute(query, ctx.guild.id, False)
        self.active_guilds.remove(ctx.guild.id)
        await ctx.tick(False)

    @antiscam.command(name='test', level=CommandLevel.Mod)
    @commands.guild_only()
    @is_server_manager()
    async def antiscam_test(self, ctx: GuildContext, *, message: str):
        """Tests to see if a message is safe"""
        res = AntiScamResult(message)
        score = res.calculate()
        await ctx.send(f"This message scored {score}% safe!")

    @antiscam.command(name='improve', level=CommandLevel.Admin)
    @commands.guild_only()
    @is_server_manager()
    async def antiscam_deposit(self, ctx: GuildContext, *, message: discord.Message):
        """
        Deposits a message so Anti-Scam can be improved.
        """
        if message.content is None:
            await ctx.send("This message cannot be reported!")
            return

        query = """INSERT INTO spam_detection (content, mentions_everyone, mention_count)
                   VALUES ($1, $2, $3)
                   ON CONFLICT DO NOTHING;"""
        await self.bot.pool.execute(query, message.content, message.mention_everyone, len(message.mentions))
        await ctx.tick(True)


async def setup(bot: LightningBot):
    await bot.add_cog(AntiScam(bot))


if __name__ == "__main__":
    class Author:
        def __init__(self) -> None:
            self.joined_at = discord.utils.utcnow()
    samples = [
        "18+ Teen Girls and onlyfans leaks for free 🍑 here @everyone. https://discord.gg/123456",
        "@everyone Best OnlyFans Leaks & Teen Content 🍑 🔞 discord.gg/123456",
        "# Teen content and onlyfans leaks here 🍑 🔞 : https://discord.gg/123456 @everyone @here",
        "@everyone\nBEST NUDES 💦 + Nitro Giveaway 🥳\nJOIN RIGHT NOW: https://discord.gg/123456",
        "50$ for Steam - [steamcommunity.com/gift/7441553](https://test.cloud/1234)"
    ]
    test = ["did you see her onlyfans", "onlyfans lmao", "go away", "check out the new steam game"]
    multi = samples + test
    for sample in multi:
        class Message:
            def __init__(self, content) -> None:
                self.mention_everyone = True
                self.content = content
                self.author = Author()
        print(sample, "Score", AntiScamResult(Message(sample)).calculate())
