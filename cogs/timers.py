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

from datetime import datetime
from discord.ext import commands
import traceback
import discord
import config
import json
from utils import time
from utils.errors import TimersUnavailable
import textwrap

STIMER = "%Y-%m-%d %H:%M:%S (UTC)"


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(usage="<when>", aliases=["timer", "reminder"],
                    invoke_without_command=True)
    async def remind(self, ctx, *, when: time.UserFriendlyTime(default='something')):
        """Reminds you of something after a certain date.

        The input can be any direct date (e.g. YYYY-MM-DD)
        or a human readable offset.

        Examples:
        - ".remind in 2 days do essay" (2 days)
        - ".remind 1 hour do dishes" (1 hour)
        - ".remind 60s clean" (60 seconds)

        Times are in UTC.
        """
        # Shoutouts to R.Danny for the UserFriendlyTime Code
        duration_text = time.natural_timedelta(when.dt, source=ctx.message.created_at)
        safe_description = await commands.clean_content().convert(ctx, str(when.arg))

        timer = self.bot.get_cog('TasksManagement')
        if not timer:
            raise TimersUnavailable
        to_dump = {"reminder_text": safe_description,
                   "author": ctx.author.id, "channel": ctx.channel.id}
        await timer.add_job("reminder", ctx.message.created_at,
                            when.dt, to_dump)
        await ctx.send(f"{ctx.author.mention}: I'll remind you in "
                       f"{duration_text} about {safe_description}.")

    @remind.command(name="list")
    async def listreminders(self, ctx):
        """Lists up to 10 of your reminders"""
        query = """SELECT id, expiry, extra
                   FROM timers
                   WHERE event = 'reminder'
                   AND extra ->> 'author' = $1
                   ORDER BY expiry
                   LIMIT 10;
                """
        rem = await self.bot.db.fetch(query, str(ctx.author.id))
        embed = discord.Embed(title="Reminders", color=discord.Color(0xf74b06))
        if len(rem) == 0:
            embed.description = "No reminders were found!"
            return await ctx.send(embed=embed)
        # Kinda hacky-ish code
        try:
            for job in rem:
                ext = json.loads(job['extra'])
                timed_txt = time.natural_timedelta(job['expiry'], suffix=True)
                # Safe Value
                reminder_text_s = textwrap.shorten(ext['reminder_text'], width=512)
                embed.add_field(name=f"{job['id']}: In {timed_txt}",
                                value=reminder_text_s, inline=False)
        except Exception:
            self.bot.log.error(traceback.format_exc())
            log_channel = self.bot.get_channel(config.powerscron_errors)
            await log_channel.send(f"PowersCron has Errored! "
                                   f"```{traceback.format_exc()}```")
            embed.description = "Something went wrong getting your timers!"\
                                " Try again later"
        await ctx.send(embed=embed)

    @remind.command(name="delete", aliases=['cancel', 'stop'])
    @commands.bot_has_permissions(add_reactions=True)
    async def deletereminder(self, ctx, *, reminder_id: int):
        """Deletes a reminder by ID.

        You can get the ID of a reminder with .listreminders

        You must own the reminder to remove it"""

        query = """DELETE FROM timers
                   WHERE id = $1
                   AND event = 'reminder'
                   AND extra ->> 'author' = $2;
                """
        async with self.bot.db.acquire() as con:
            result = await con.execute(query, reminder_id, str(ctx.author.id))
        if result == 'DELETE 0':
            await ctx.message.add_reaction("❌")
            return await ctx.send(f"I couldn't delete a reminder with that ID!")

        await ctx.send(f"Successfully deleted reminder (ID: {reminder_id})")
        await ctx.message.add_reaction("✅")  # For whatever reason

    @commands.command(name="current-utc-time")
    async def currentutctime(self, ctx):
        """Sends the current time in UTC"""
        await ctx.send(f"It is currently "
                       f"`{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`")

    @commands.Cog.listener()
    async def on_reminder_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        channel = self.bot.get_channel(ext['channel'])
        uid = await self.bot.fetch_user(ext['author'])
        timed_txt = time.natural_timedelta(jobinfo['created'],
                                           source=jobinfo['expiry'],
                                           suffix=True)
        try:
            await channel.send(f"{uid.mention}: "
                               "You asked to be reminded "
                               f"{timed_txt} "
                               f"about `{ext['reminder_text']}`")
        # Attempt to DM User if we failed to send Reminder
        except discord.errors.Forbidden:
            try:
                await uid.send(f"{uid.mention}: "
                               "You asked to be reminded "
                               f"{timed_txt} "
                               f"about `{ext['reminder_text']}`")
            except Exception:
                # Optionally add to the db as a failed job
                self.bot.log.error(f"Failed to remind {ext['author']}.")
                pass


def setup(bot):
    bot.add_cog(Reminders(bot))
