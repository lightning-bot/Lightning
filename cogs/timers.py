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
from datetime import datetime
from discord.ext import commands
import traceback
import discord
import config
import json

class Timers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["addreminder", "timer"])
    async def remind(self, ctx, when: str, *, description: str = "something"):
        """Reminds you of something after a certain date.
        
        Examples:
        - ".remind 1d do essay" (1 day)
        - ".remind 1h do dishes" (1 hour)
        - ".remind 60s clean" (60 seconds)
        """
        current_timestamp = time.time()
        expiry_timestamp = self.bot.parse_time(when)

        if current_timestamp + 4 > expiry_timestamp:
            await ctx.send(f"{ctx.author.mention}: Minimum "
                            "remind interval is 5 seconds.")
            return

        expiry_datetime = datetime.utcfromtimestamp(expiry_timestamp)
        duration_text = self.bot.get_relative_timestamp(time_to=expiry_datetime,
                                                        include_to=True,
                                                        humanized=True)
        safe_description = await commands.clean_content().convert(ctx, str(description))

        query = """INSERT INTO cronjobs (event, created, expiry, extra)
                   VALUES ($1, $2, $3, $4::jsonb);
                """
        to_dump = {"reminder_text": safe_description, 
                   "author": ctx.author.id, "channel": ctx.channel.id}
        await self.bot.db.execute(query, "reminder", datetime.utcnow(), 
                                  expiry_datetime, 
                                  json.dumps(to_dump))
        await ctx.send(f"{ctx.author.mention}: I'll remind you in {duration_text}.")

    @commands.command(aliases=['listreminds', 'listtimers'])
    async def listreminders(self, ctx):
        """Lists up to 10 of your reminders"""
        query = """SELECT id, expiry, extra
                   FROM cronjobs
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
                #expiry_timestr = datetime.utcfromtimestamp(job['expiry'])
                        #.strftime('%Y-%m-%d %H:%M:%S (UTC)')
                ext = json.loads(job['extra'])
                duration_text = self.bot.get_relative_timestamp(time_to=job['expiry'],
                                                                include_to=True,
                                                                humanized=True)
                embed.add_field(name=f"{job['id']}: In {duration_text}", 
                                value=f"{ext['reminder_text']}")
        except:
            self.bot.log.error(traceback.format_exc())
            log_channel = self.bot.get_channel(config.powerscron_errors)
            await log_channel.send(f"PowersCron has Errored! "
                                   f"```{traceback.format_exc()}```")
            embed.description = "Something went wrong getting your timers!"\
                                " Try again later"
        await ctx.send(embed=embed)

    @commands.command(aliases=['deletetimer', 'removereminder'])
    async def deletereminder(self, ctx, *, reminder_id: int):
        """Deletes a reminder by ID.
        
        You can get the ID of a reminder with .listreminders

        You must own the reminder to remove it"""

        query = """DELETE FROM cronjobs
                   WHERE id = $1
                   AND event = 'reminder'
                   AND extra ->> 'author' = $2;
                """
        result = await self.bot.db.execute(query, reminder_id, str(ctx.author.id))
        if result == 'DELETE 0':
            await ctx.message.add_reaction("❌")
            return await ctx.send(f"I couldn't delete a reminder with that ID!")            

        await ctx.send(f"Successfully deleted reminder (ID: {reminder_id})")
        await ctx.message.add_reaction("✅") # For whatever reason

def setup(bot):
    bot.add_cog(Timers(bot))