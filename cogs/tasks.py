# Lightning.py - A multi-purpose Discord bot
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

import asyncio
import json
import os
import random
import subprocess
import traceback
from datetime import datetime

import asyncpg
import discord
from bolt.time import get_relative_timestamp
from discord.ext import commands, tasks

from utils.checks import is_bot_manager
from utils.nin_updates import nintendo_updates_feed


class RemoveRestrictionError(Exception):
    pass


STIMER = "%Y-%m-%d %H:%M:%S (UTC)"
C_HASH = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('UTF-8')


class TasksManagement(commands.Cog):
    """Commands that help manage the bot's background tasks and loops"""
    def __init__(self, bot):
        self.bot = bot
        self.statuses = json.load(open('resources/status_switching.json',
                                       'r', encoding='utf8'))
        self.status_rotate.start()
        self.dispatch_jobs = self.bot.loop.create_task(self.do_jobs())
        self.stability.start()

    # Here we cancel our loops on cog unload
    def cog_unload(self):
        self.dispatch_jobs.cancel()
        self.status_rotate.cancel()
        self.stability.cancel()

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
        return id[0]
        # Adding temporary timers in the database for those
        # moments when the bot decides to go down.
        # stime = (expiry - created).total_seconds()
        # if stime <= 60:
        #    timer = {"id": id[0], "event": event, 'created': created,
        #             'expiry': expiry, "extra": json.dumps(extra)}
        # A loop for small timers
        #    self.bot.loop.create_task(self.short_timers(stime, timer))
        #    return

    async def randomize_status(self):
        ext_list = [f"on commit {C_HASH}", [3, f"{len(self.bot.guilds)} servers"],
                    f"on {self.bot.config['bot']['version']}"]
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
        cquery = """SELECT COUNT(*) FROM timers WHERE event=$1"""
        con = await self.bot.db.acquire()
        try:
            table = await con.fetch(query, jobtype)
            result = await con.fetchval(cquery, jobtype)
        finally:
            await self.bot.db.release(con)
        embed = discord.Embed(title="Active Timers", color=0xf74b06)
        embed.set_footer(text=f"{result} running timers for {jobtype}")
        try:
            for job in table:
                duration_text = get_relative_timestamp(time_to=job['expiry'],
                                                       include_to=True)
                embed.add_field(name=f"{jobtype} {job['id']}",
                                value=f"Expiry: {duration_text}\n"
                                      f"Extra Details: {job['extra']}")
        except Exception:
            self.bot.log.error(f"Tasks ERROR: "
                               f"{traceback.format_exc()}")
            wbhk = discord.Webhook.from_url
            adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
            webhook = wbhk(self.bot.config['logging']['timer_errors'], adapter=adp)
            await webhook.execute(f"Tasks has Errored!\n"
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
            jobs = await self.bot.db.fetch(query)
            timestamp = datetime.utcnow()
            try:
                for jobtype in jobs:
                    if len(jobtype) == 0:
                        # Can we close our loop?
                        self._timers_chk = None
                        return
                    if timestamp >= jobtype['expiry']:
                        # Dispatch the job and delete it.
                        query = "DELETE FROM timers WHERE id=$1;"
                        await self.bot.db.execute(query, jobtype['id'])
                        self.bot.dispatch(f"{jobtype['event']}_job_complete",
                                          jobtype)
            except (discord.ConnectionClosed, asyncpg.PostgresConnectionError):
                self.dispatch_jobs.cancel()
                self.dispatch_jobs = self.bot.loop.create_task(self.do_jobs())
            except Exception:
                # Keep jobs for now if they errored
                self.bot.log.error(f"Timers ERROR: "
                                   f"{traceback.format_exc()}")
                wbhk = discord.Webhook.from_url
                adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
                webhook = wbhk(self.bot.config['logging']['timer_errors'], adapter=adp)
                await webhook.execute(f"Timers has Errored!\n"
                                      f"```{traceback.format_exc()}```")

            await asyncio.sleep(1)

    @tasks.loop(minutes=7)
    async def status_rotate(self):
        if self.bot.config['bot']['status_rotate']:
            await self.randomize_status()
        else:
            self.status_rotate.cancel()

    @status_rotate.before_loop
    async def sr_prep(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=45)
    async def stability(self):
        await nintendo_updates_feed(self.bot)

    @stability.before_loop
    async def stability_load(self):
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

    # @commands.Cog.listener()
    # async def on_guild_leave(self, guild):
    #    to_clean = self.guild_cleanup()
    #    gid = str(guild.id)
    #    if gid not in to_clean['guildids']:
    #        to_clean['guildids'].append(gid)
    #        dec = self.bot.parse_time("30 days")
    #        await self.add_job("guild_clean", datetime.utcnow(), dec,
    #                           {"guild_id": guild.id})
    #    self.clean_guilds_dump(to_clean)


def setup(bot):
    bot.add_cog(TasksManagement(bot))
