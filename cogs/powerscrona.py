# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

import time
import config
from datetime import datetime
from discord.ext import commands, tasks
import asyncio
import traceback
import discord
from utils.checks import is_bot_manager
import subprocess
import random
import json
import dbl
import os

class RemoveRestrictionError(Exception):
    pass

STIMER = "%Y-%m-%d %H:%M:%S (UTC)"
C_HASH = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('UTF-8')

class PowersCronManagement(commands.Cog):
    """Commands that help manage PowersCron's Cron Jobs"""
    def __init__(self, bot):
        self.bot = bot
        self.statuses = json.load(open('resources/status_switching.json', 
                                       'r', encoding='utf8'))
        self.status_rotate.start()
        self.dispatch_jobs = self.bot.loop.create_task(self.do_jobs())
        #self.cron_6_hours.start()
        self.cron_hourly.start()
        self.discordbotlist = dbl.DBLClient(self.bot, config.dbl_token)

    # Here we cancel our loops on cog unload
    def cog_unload(self):
        self.dispatch_jobs.cancel()
        self.status_rotate.cancel()
        #Not being used since we moved over to postgresql
        #self.cron_6_hours.cancel() 
        self.cron_hourly.cancel()

    async def cog_command_error(self, ctx, error):
        if isinstance(error, RemoveRestrictionError):
            self.bot.log.error(error)

    async def short_timers(self, seconds, timerinfo):
        """A short loop for the bot to process small timers 
        that are 5 seconds or less"""
        await asyncio.sleep(seconds)
        async with self.bot.db.acquire() as con:
            query = "DELETE FROM timers WHERE id=$1;"
            await con.execute(query, timerinfo['id'])
        self.bot.dispatch(f"{timerinfo['event']}_job_complete", timerinfo)

    async def add_job(self, event: str, created, expiry, extra):
        """Adds a job/pending timer to the Timer System
        
        Arguments:
        -------------
        event: str
            The name of the event to trigger. 
            Valid events are timed_restriction, timeban, timeblock, 
            guild_clean, and reminder
        created: datetime.datetime
            The creation of the timer.
        expiry: datetime.datetime
            When the job should be done.
        extra: json
            Extra info related to the timer
        """
        if extra:
            query = """INSERT INTO timers (event, created, expiry, extra)
                       VALUES ($1, $2, $3, $4::jsonb)
                       RETURNING id;
                    """
            connect = await self.bot.db.acquire()
            try:
                id = await connect.fetchrow(query, event, created, expiry, json.dumps(extra))
            finally:
                await self.bot.db.release(connect)
        else:
            query = """INSERT INTO timers (event, created, expiry)
                       VALUES ($1, $2, $3)
                       RETURNING id;
                    """
            connect = await self.bot.db.acquire()
            try:
                id = await connect.fetchrow(query, event, created, expiry)
            finally:
                await self.bot.db.release(connect)
        # Adding temporary timers in the database for those 
        # moments when the bot decides to go down.
        #stime = (expiry - created).total_seconds()
        #if stime <= 60:
        #    timer = {"id": id[0], "event": event, 'created': created, 
        #             'expiry': expiry, "extra": json.dumps(extra)}
            # A loop for small timers
        #    self.bot.loop.create_task(self.short_timers(stime, timer))
        #    return

    async def randomize_status(self):
        ext_list = [f"on commit {C_HASH}", [3, f"{len(self.bot.guilds)} servers"], 
                    f"on {self.bot.version}"]
        msg = random.randint(1, 2)
        if msg == 1:
            msg = random.choice(self.statuses)
        elif msg == 2:
            msg = random.choice(ext_list)
        g_type = 0
        if isinstance(msg, list):
            g_type, msg = msg

        st_msg = f"{msg} "
        await self.bot.change_presence(activity=discord.Activity(type=g_type, name=st_msg))

    @commands.check(is_bot_manager)
    @commands.command(aliases=['deletejobs'])
    async def deletejob(self, ctx, jobtype: str, job_id: int):
        """Deletes a job/timer from the database
        
        You'll need to provide:
        - Type (The type of job it is. Ex: timeban)
        - ID (The ID of the Job.)
        """
        query = """DELETE FROM timers 
                WHERE event=$1 AND id=$2;
                """
        connect = await self.bot.db.acquire()
        try:
            await connect.execute(query, jobtype, job_id)
        finally:
            await self.bot.db.release(connect)
        await ctx.send(f"Successfully deleted {jobtype} with an ID of {job_id}")

    @commands.check(is_bot_manager)
    @commands.command()
    async def listjobs(self, ctx, jobtype: str = "reminder"):
        """Lists up to 10 jobs of a certain jobtype

        Jobtypes can be either:
        - reminder
        - timeban
        - timed_restriction
        - timeblock
        """
        query = """SELECT id, expiry, extra
                   FROM timers
                   WHERE event=$1
                   ORDER BY expiry
                   LIMIT 10;
                """
        con = await self.bot.db.acquire()
        try:
            table = await con.fetch(query, jobtype)
        finally:
            await self.bot.db.release(con)
        embed = discord.Embed(title="Active Timers", color=0xf74b06)
        # It just works:tm:
        query = """SELECT COUNT(*) FROM timers WHERE event=$1"""
        async with self.bot.db.acquire() as con:
            result = await con.fetch(query, jobtype)
        embed.set_footer(text=f"{result[0][0]} running timers for {jobtype}")
        try:
            for job in table:
                duration_text = self.bot.get_relative_timestamp(time_to=job['expiry'],
                                                                include_to=True,
                                                                humanized=True)
                embed.add_field(name=f"{jobtype} {job['id']}", 
                                value=f"Expiry: {duration_text}\n"
                                      f"Extra Details: {job['extra']}")
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
            query = """SELECT * FROM timers;"""
            async with self.bot.db.acquire() as con:
                jobs = await con.fetch(query)
            timestamp = datetime.utcnow()
            try:
                for jobtype in jobs:
                    if len(jobtype) == 0:
                        # Can we close our loop?
                        self._timers_chk = None
                        return
                    if timestamp >= jobtype['expiry']:
                        # Dispatch the job and delete it.
                        async with self.bot.db.acquire() as con:
                            query = "DELETE FROM timers WHERE id=$1;"
                            await con.execute(query, jobtype['id'])
                        self.bot.dispatch(f"{jobtype['event']}_job_complete", 
                                          jobtype)
            except:
                # Keep jobs for now if they errored
                self.bot.log.error(f"Timers ERROR: "
                                   f"{traceback.format_exc()}")
                wbhk = discord.Webhook.from_url
                adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
                webhook = wbhk(config.powerscron_errors, adapter=adp)
                await webhook.execute(f"Timers has Errored!\n"
                                      f"```{traceback.format_exc()}```")

            await asyncio.sleep(1)

    @tasks.loop(minutes=7)
    async def status_rotate(self):
        while not self.bot.is_closed():
            await self.randomize_status()
            await asyncio.sleep(7 * 60) # Use our same value here

    @status_rotate.before_loop
    async def sr_prep(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=6)
    async def cron_6_hours(self):
        while not self.bot.is_closed():
            try:
                await self.send_db()
            except:
                wbhk = discord.Webhook.from_url
                adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
                webhook = wbhk(config.powerscron_errors, adapter=adp)
                await webhook.execute("PowersCron 6 Hours has Errored:"
                                      f"```{traceback.format_exc()}```")
            await asyncio.sleep(21600) # 6 Hours

    @cron_6_hours.before_loop
    async def c_6hr_prep(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def cron_hourly(self):
        try:
            self.bot.log.info("Attempting to Post Guild Count to DBL")
            await self.discordbotlist.post_guild_count()
            self.bot.log.info("Successfully posted guild count!")
        except Exception as e:
            self.bot.log.error(f"PowersCron Hourly ERROR: {e}\n---\n"
                               f"{traceback.print_exc()}")
            wbhk = discord.Webhook.from_url
            adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
            webhook = wbhk(config.powerscron_errors, adapter=adp)
            await webhook.execute(f"PowersCron Hourly has Errored!\n"
                                  f"```{traceback.format_exc()}```")
        await asyncio.sleep(3600)
    
    @cron_hourly.before_loop
    async def cron_hourly_before_loop(self):
        await self.bot.wait_until_ready()

    # LightningClean - Lightning's File Cleanup System
    def guild_cleanup(self):
        os.makedirs("config", exist_ok=True)
        if os.path.isfile("config/guilds_to_clean.json"):
            with open("config/guilds_to_clean.json", "r") as blacklist:
                return json.load(blacklist)
        else:
            return {"guildids": []}

    def clean_guilds_dump(self, json_returned):
        os.makedirs("config", exist_ok=True)
        with open("config/guilds_to_clean.json", "w") as f:
            return json.dump(json_returned, f)

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        to_clean = self.guild_cleanup()
        gid = str(guild.id)
        if gid not in to_clean['guildids']:
            to_clean['guildids'].append(gid)
            dec = self.bot.parse_time("30 days")
            await self.add_job("guild_clean", datetime.utcnow(), dec, 
                               {"guild_id": guild.id})
        self.clean_guilds_dump(to_clean)

def setup(bot):
    bot.add_cog(PowersCronManagement(bot))