"""
Lightning.py - A personal Discord bot
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
import json
import random
from logging import Logger, getLogger

from discord import Activity, ActivityType
from discord.ext import tasks

from lightning import LightningBot, LightningCog

log: Logger = getLogger(__name__)


class Switchy(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot

        with open("resources/songs.json", "r") as fp:
            songs = json.load(fp)

        self.s1_songs = songs['1']
        self.s2_songs = songs['2']
        self.s3_songs = songs['3']
        self.s4_songs = songs['4']

        self.switchy.start()

    def cog_unload(self):
        self.switchy.cancel()

    @tasks.loop(minutes=5)  # This would be :verycool: if I made this change dynamically to match each song's length
    async def switchy(self):
        await self.bot.wait_until_ready()

        season = self.bot.config['bot'].get('season', random.randint(1, 4))
        songs = getattr(self, f"s{season}_songs", self.s1_songs)
        song = random.choice(songs)
        log.debug(f"Changing presence to {song}")
        await self.bot.change_presence(activity=Activity(name=song, type=ActivityType.listening))

    @switchy.after_loop
    async def on_switchy_cancel(self):
        if not self.bot.is_closed():
            # TBH we should reset it back to the presence it was before
            await self.bot.change_presence()


def setup(bot: LightningBot) -> None:
    bot.add_cog(Switchy(bot))
