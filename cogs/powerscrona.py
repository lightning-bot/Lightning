import dataset
import time
import config
from datetime import datetime
from discord.ext import commands, tasks
import asyncio
import traceback
import discord
from utils.bot_mgmt import check_if_botmgmt
from enum import Enum
import subprocess
import random
import json
from utils.restrictions import remove_restriction

# We'll use a Enum just for the sake of not redo-ing this status switching code.
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

STIMER = "%Y-%m-%d %H:%M:%S (UTC)"
C_HASH = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('UTF-8')

class PowersCronManagement(commands.Cog):
    """Commands that help manage PowersCron's Cron Jobs"""
    def __init__(self, bot):
        self.bot = bot
        self.stats_ran = random.choice(list(Names))
        self.music = json.load(open('resources/music_list.json', 'r'))
        self.status_rotate.start()
        self.dispatch_jobs = self.bot.loop.create_task(self.do_jobs())
        self.cron_6_hours.start()
        self.db = dataset.connect('sqlite:///config/powerscron.sqlite3')
        self.bot.log.info(f'{self.qualified_name} loaded')

    # Here we cancel our loops on cog unload
    def cog_unload(self):
        self.dispatch_jobs.cancel()
        self.status_rotate.cancel()
        self.cron_6_hours.cancel()

    async def send_db(self):
        back_chan = self.bot.get_channel(config.powerscron_backups)
        files = ["config/powerscron.sqlite3", "config/database.sqlite3"]
        await back_chan.send("6 hour data backup:", 
                             files=[discord.File(f) for f in files])

    @commands.check(check_if_botmgmt)
    @commands.command()
    async def fetchcrondb(self, ctx):
        """Fetches the PowersCron Database File"""
        try:
            await ctx.author.send("Here's the current database file:", 
                                  file=discord.File("config/powerscron.sqlite3"))
        except discord.errors.Forbidden:
            return await ctx.send(f"💢 I couldn't send the log "
                                  "file in your DMs. Please resolve this.")

    @commands.check(check_if_botmgmt)
    @commands.command(aliases=['deletejobs'])
    async def deletejob(self, ctx, jobtype: str, timestamp: int, job_id: int):
        """Deletes a job from the database
        
        You'll need to provide:
        - Type (The type of job it is. Ex: timeban)
        - Timestamp (The timestamp of the job)
        - ID (The ID of the Job.)

        You can get this from fetchcrondb
        """
        self.db['cron_jobs'].delete(job_type=jobtype, expiry=timestamp, id=job_id)
        await ctx.send(f"Successfully deleted {jobtype} with an ID of {job_id}")

    @commands.check(check_if_botmgmt)
    @commands.command()
    async def listjobs(self, ctx, jobtype: str = "reminder"):
        """Lists up to 10 jobs of a certain jobtype

        Jobtypes can be either:
        - reminder
        - timeban
        - timemute
        """
        table = self.db["cron_jobs"].find(job_type=jobtype, _limit=10)
        ctable = self.db["cron_jobs"].count(job_type=jobtype)
        embed = discord.Embed(title="Active PowersCron Jobs", color=discord.Color(0xf74b06))
        try:
            embed.set_footer(text=f"There are currently {ctable} running"
                                  f" PowersCron Jobs for {jobtype}")
            for job in table:
                expiry_timestr = datetime.utcfromtimestamp(job['expiry'])
                duration_text = self.bot.get_relative_timestamp(time_to=expiry_timestr,
                                                                include_to=True,
                                                                humanized=True)
                embed.add_field(name=f"{job['job_type']} {job['id']}", 
                                value=f"{duration_text}\nRaw Timestamp:"
                                      f" {job['expiry']}")
        except:
            self.bot.log.error(f"PowersCron ERROR: "
                               f"{traceback.format_exc()}")
            log_channel = self.bot.get_channel(config.powerscron_errors)
            await log_channel.send(f"PowersCron has Errored! "
                                   f"```{traceback.format_exc()}```")
            embed.description = "Something went wrong grabbing jobs!"\
                                " Try again later(?)"
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(aliases=['stopstatus'])
    async def stop_ss(self, ctx):
        """Stops the status rotation loop"""
        self.status_rotate.cancel()
        await ctx.send("Status Switcher has been halted! 🛑")

    @commands.is_owner()
    @commands.command(aliases=['restartstatus', 'startstatus'])
    async def start_ss(self, ctx):
        """(Re)starts the status rotation loop"""
        self.status_rotate.start()
        await ctx.send("Status Switcher has started (again)! ✅")

    async def do_jobs(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            jobs = self.db['cron_jobs'].all()
            timestamp = time.time()
            try:
                for jobtype in jobs:
                    expiry2 = jobtype['expiry']
                    if timestamp > expiry2:
                        if jobtype['job_type'] == "reminder":
                            channel = self.bot.get_channel(jobtype['channel'])
                            await channel.send(f"<@{jobtype['author']}>: "
                                               "You asked to be reminded "
                                               "on "
                                               f"{jobtype['job_added'].strftime(STIMER)} "
                                               f"about `{jobtype['remind_text']}`")
                            # Delete the timer
                            self.db['cron_jobs'].delete(author=jobtype['author'], 
                                                        expiry=expiry2,
                                                        job_type="reminder")
                        elif jobtype['job_type'] == "timeban":
                            guid = self.bot.get_guild(jobtype['guild_id'])
                            uid = await self.bot.fetch_user(jobtype['user_id'])
                            await guid.unban(uid, reason="PowersCron: "
                                             "Timed Ban Expired.")
                            # Delete the scheduled unban
                            self.db['cron_jobs'].delete(job_type="timeban", 
                                                        expiry=expiry2, 
                                                        user_id=jobtype['user_id'])
                        elif jobtype['job_type'] == "timemute":
                            guild = self.bot.get_guild(jobtype['guild_id'])
                            user = guild.get_member(jobtype['user_id'])
                            role = guild.get_role(jobtype['role_id'])
                            remove_restriction(guild, jobtype['user_id'], jobtype['role_id'])
                            await user.remove_roles(role, reason="PowersCron: "
                                                    "Timed Mute Expired.")
                            # Delete the scheduled unmute
                            self.db['cron_jobs'].delete(job_type="timemute", 
                                                        expiry=expiry2,
                                                        guild_id=jobtype['guild_id'],
                                                        user_id=jobtype['user_id'])
            except:
                # Keep jobs for now if they errored
                self.bot.log.error(f"PowersCron ERROR: "
                                   f"{traceback.format_exc()}")
                log_channel = self.bot.get_channel(config.powerscron_errors)
                await log_channel.send(f"PowersCron has Errored! "
                                       f"```{traceback.format_exc()}```")

            await asyncio.sleep(5)

    @tasks.loop(minutes=7)
    async def status_rotate(self):
        await self.bot.wait_until_ready()           
        while not self.bot.is_closed():
            if self.stats_ran is Names.SERVERS:
                act_name = f"{len(self.bot.guilds)} servers"
                act_type = discord.ActivityType.watching
            if self.stats_ran is Names.GIT_COMMIT:
                act_name = f"Running on commit {C_HASH}"
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
            await asyncio.sleep(7 * 60) # Use our same value here

    @tasks.loop(hours=6)
    async def cron_6_hours(self):
        errors_chan = self.bot.get_channel(config.powerscron_errors)
        while not self.bot.is_closed():
            try:
                await self.send_db()
            except:
                await errors_chan.send("PowersCron 6 Hours has Errored:"
                                       f"```{traceback.format_exc()}```")
            await asyncio.sleep(21600) # 6 Hours

    @cron_6_hours.before_loop
    async def c_6hr_prep(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(PowersCronManagement(bot))