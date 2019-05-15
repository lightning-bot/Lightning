import asyncio
import discord
from discord.ext import commands #, tasks
import random
import datetime
import subprocess
import json
from enum import Enum

# We'll use a Enum just for the sake of not redo-ing this code over again.
class Names(Enum):
    SERVERS = 0
    GIT_COMMIT = 1
    VERSION = 2
    DEF_HELP = 3
    MEMBERS = 4
    MUSIC = 5

    def change(self):
        num = list(self.__class__)
        index = num.index(self) + 1
        if index >= len(num):
            index = 0
        return num[index]


class StatusSwitch(commands.Cog):
    """Playing status stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')
        self.stats_ran = random.choice(list(Names))
        self.music = json.load(open('resources/music_list.json', 'r'))
        self.rotate_task = self.bot.loop.create_task(self.status_rotate())       

    #def cog_unload(self):
    #    self.status_rotate.cancel()


    #@tasks.loop(seconds=25.0, reconnect=True, loop=True)
    async def status_rotate(self):
        await self.bot.wait_until_ready()           
        while not self.bot.is_closed():
            #switch_time = self.stats_ran()
            if self.stats_ran is Names.SERVERS:
                act_name = f"{len(self.bot.guilds)} servers"
                act_type = discord.ActivityType.watching
            if self.stats_ran is Names.GIT_COMMIT:
                act_name = f"Running on commit {subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('UTF-8')}"
                act_type = discord.ActivityType.playing
            if self.stats_ran is Names.VERSION:
                act_name = f"on {self.bot.version}"
                act_type = discord.ActivityType.playing
            if self.stats_ran is Names.DEF_HELP:
                act_name = f"for l.help"
                act_type = discord.ActivityType.watching
            if self.stats_ran is Names.MEMBERS:
                act_name = f"{len(self.bot.users)} users"
                act_type = discord.ActivityType.watching
            if self.stats_ran is Names.MUSIC:
                act_name = f"♬ {random.choice(self.music)}"
                act_type = discord.ActivityType.playing

            
            await self.bot.change_presence(activity=discord.Activity(name=act_name, type=act_type))
            self.stats_ran = self.stats_ran.change()
            await asyncio.sleep(5 * 60) # 5 Minutes * 60 Seconds
    
    #async def rotate_loop(self):
    #   try:
    #        await self.stats_ran()
    #        await self.status_rotate()
    #        await asyncio.sleep(15 * 60)
    #    except asyncio.CancelledError:
    #        pass




def setup(bot):
    bot.add_cog(StatusSwitch(bot))