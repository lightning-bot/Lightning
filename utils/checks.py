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


from discord.ext import commands
import config

def is_guild(guild_id):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
    return commands.check(predicate)

def is_git_whitelisted(ctx):
    if not ctx.guild:
        return False
    guild = (ctx.guild.id in config.gh_whitelisted_guilds)
    return (guild)

def is_one_of_guilds(guilds: list):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id in guilds:
            return True
    return commands.check(predicate)