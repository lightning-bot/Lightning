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
from __future__ import annotations

from typing import TYPE_CHECKING

from lightning import LightningCog, LightningCommand, group

if TYPE_CHECKING:
    from lightning import LightningBot, LightningContext


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
            self.memes.add_command(TextMeme(key, value, cog=self))

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


def setup(bot: LightningBot) -> None:
    bot.add_cog(Memes(bot))
