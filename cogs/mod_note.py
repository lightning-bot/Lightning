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

import discord
from discord.ext import commands
from discord.ext.commands import Cog
from db.user_log import userlog
import db.mod_check

# Robocop-ng's Note Cog, but slightly adapted. Robocop-ng's note cog is under the MIT License.
# https://github.com/reswitched/robocop-ng/blob/master/cogs/mod_note.py
class ModNote(Cog):
    def __init__(self, bot):
        """Note cog for adding a note to user. 
        Useful for not taking moderation action, but for keeping notes on a user."""
        self.bot = bot

    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    @commands.command(aliases=["addnote"])
    async def note(self, ctx, target: discord.Member, *, note: str = ""):
        """Adds a note to a user, staff only."""
        userlog(ctx.guild, target.id, ctx.author, note,
                "notes", target.name)
        await ctx.send(f"Noted {target}!")

    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    @commands.command(aliases=["addnoteid"])
    async def noteid(self, ctx, target: int, *, note: str = ""):
        """Adds a note to a user by userid, staff only."""
        userlog(ctx.guild, target, ctx.author, note,
                "notes")
        await ctx.send(f"ID {target} was noted!")


def setup(bot):
    bot.add_cog(ModNote(bot))
