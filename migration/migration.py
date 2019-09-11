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
import discord
import json
import os
from utils.user_log import set_userlog

class Migration(commands.Cog):
    """The data migration cog."""
    def __init__(self, bot):
        self.bot = bot
        
    def get_user_restrictions(self, guild, uid):
        uid = str(uid)
        with open(f"config/{guild.id}/restrictions.json", "r") as f:
            rsts = json.load(f)
            if uid in rsts:
                return rsts[uid]
            return []

    @commands.group()
    async def migrate(self, ctx):
        """Migration"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @migrate.command(name="userlog")
    @commands.is_owner()
    async def migrate_userlog(self, ctx, guild_id: int):
        """Migrates a guild's userlog.json to the database"""
        try:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                # We don't need to migrate guilds the bot isn't in
                return await ctx.send(f"Not migrating userlog.json "
                                      "since Lightning isn't there")
            if os.path.isfile(f"config/{guild.id}/userlog.json"):
                with open(f"config/{guild.id}/userlog.json") as f:
                    to_migrate = json.load(f)
                    await set_userlog(self.bot, guild, to_migrate)
                    return await ctx.send(f"Successfully migrated userlog.json for {guild_id}")
            else:
                return await ctx.send(f"{guild_id} does not have a userlog!")
        except Exception as e:
            return await ctx.send(e)

    @migrate.command(name="config")
    @commands.is_owner()
    async def migrate_config(self, ctx, guild_id: int):
        """Migrates a guild's config to the database"""
        try:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return await ctx.send("Not migrating config.json"
                                      " since Lightning isn't there")
            if os.path.isfile(f"config/{guild.id}/config.json"):
                with open(f"config/{guild.id}/config.json") as f:
                    # Do stuff here
                    data = json.load(f)
                    # Some stuff was renamed so yolo
                    config = self.bot.get_cog('Configuration')
                    if not config:
                        return await ctx.send("Cannot set guild_mod_config "
                                              "as `cogs.config` is not loaded. "
                                              "Please load it.")
                    if "log_channel" in data:
                        data['modlog_chan'] = data['log_channel']
                        data.pop('log_channel')
                    await config.set_modconfig(ctx, data)
                    await ctx.send(f"Successfully migrated {guild.id} config.json")
            else:
                return await ctx.send(f"{guild_id} does not have a config!")
        except Exception as e:
            return await ctx.send(e)

    @migrate.command(name="autoroles")
    @commands.is_owner()
    async def migrate_autoroles(self, ctx):
        """Migrates autoroles to psql"""
        failed = 0
        query = """INSERT INTO auto_roles
                VALUES ($1, $2);
                """
        data = json.load(open("migration/output/autoroles.json", "r"))
        for r in data["results"]:
            async with self.bot.db.acquire() as con:
                try:
                    await con.execute(query, r["guild_id"], r['role_id'])
                except:
                    failed += 1
        sub = data["count"] - failed
        await ctx.send(f"{sub} were migrated. "
                       f"{failed} failed to migrate.")

    @migrate.command(name="staffroles")
    @commands.is_owner()
    async def migrate_staffroles(self, ctx):
        """Migrates staff roles to psql."""
        failed = 0
        query = """INSERT INTO staff_roles VALUES (guild_id, role_id, perms)
                VALUES ($1, $2, $3);
                """
        data = json.load(open("migration/output/staff_roles.json", "r"))
        for r in data["results"]:
            async with self.bot.db.acquire() as con:
                try:
                    await con.execute(query, r['guild_id'], r['role_id'], r['staff_perms'])
                except:
                    failed += 1
        sub = data["count"] - failed
        await ctx.send(f"{sub} were migrated. "
                       f"{failed} failed to migrate.")

def setup(bot):
    bot.add_cog(Migration(bot))