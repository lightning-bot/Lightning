import dataset
import time
import config
from datetime import datetime
from discord.ext import commands
import asyncio
import traceback
import discord
from utils.bot_mgmt import check_if_botmgmt

STIMER = "%Y-%m-%d %H:%M:%S (UTC)"

class PowersCronManagement(commands.Cog):
    """Commands that help manage PowersCron's Cron Jobs"""
    def __init__(self, bot):
        self.bot = bot
        self.dispatch_jobs = self.bot.loop.create_task(self.do_jobs())
        self.db = dataset.connect('sqlite:///config/powerscron.sqlite3')
        self.bot.log.info(f'{self.qualified_name} loaded')

    # Here we cancel our do_jobs loop on cog unload
    def cog_unload(self):
        self.dispatch_jobs.cancel()

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

            except:
                # Keep jobs for now if they errored
                self.bot.log.error(f"PowersCron ERROR: "
                                   f"{traceback.format_exc()}")
                log_channel = self.bot.get_channel(config.powerscron_errors)
                await log_channel.send(f"PowersCron has Errored! "
                                       f"```{traceback.format_exc()}```")

            await asyncio.sleep(5)



def setup(bot):
    bot.add_cog(PowersCronManagement(bot))
