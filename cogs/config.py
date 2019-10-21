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

# TODO: Add plonks

import discord
from discord.ext import commands
from typing import Union
import json
import resources.botemojis as emoji
import asyncpg


class Prefix(commands.Converter):
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>', "l.")):
            raise commands.BadArgument('That is a reserved prefix already in use.')
        if len(argument) > 35:
            raise commands.BadArgument('You can\'t have a prefix longer than 35 characters!')
        return argument


class Configuration(commands.Cog):
    """Server Configuration Commands"""
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def grab_modconfig(self, ctx):
        """Grabs a guild's mod_config and returns json"""
        query = """SELECT log_channels FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        ret = await self.bot.db.fetchrow(query, ctx.guild.id)
        if ret:
            if ret['log_channels']:
                guild_config = json.loads(ret['log_channels'])
            else:
                guild_config = {}
        else:
            guild_config = {}

        return guild_config

    async def set_modconfig(self, ctx, to_dump):
        """Sets a mod config for a guild and
        dumps what's passed in to_dump. """
        query = """INSERT INTO guild_mod_config (guild_id, log_channels)
                   VALUES ($1, $2::jsonb)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET log_channels = EXCLUDED.log_channels;"""
        await self.bot.db.execute(query, ctx.guild.id,
                                  json.dumps(to_dump))

    @commands.command(name="settings")
    @commands.has_permissions(manage_guild=True)
    async def view_guild_settings(self, ctx):
        """Views the guild's settings for the bot"""
        em = discord.Embed(title=f"Settings for {ctx.guild.name}", color=0xf74b06)
        query = """SELECT * FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        con = await self.bot.db.acquire()
        try:
            ret = await con.fetchrow(query, ctx.guild.id)
            if not ret:
                await ctx.send(f"Could not retrieve any settings!")
                await self.bot.db.release(con)
                return
            if ret['mute_role_id']:
                role = discord.utils.get(ctx.guild.roles, id=ret['mute_role_id'])
                if not role:
                    # Remove our mute role if it's missing
                    query = """UPDATE guild_mod_config
                               SET mute_role_id=NULL
                               WHERE guild_id=$1;
                            """
                    await con.execute(query, ctx.guild.id)
        finally:
            await self.bot.db.release(con)
        if ret['log_channels']:
            logging = json.loads(ret['log_channels'])
            log_info = {"join_log_embed_channel": "Embedded Join & Leave Logs",
                        "join_log_channel": "Compact Join & Leave Logs",
                        "event_channel": "Compact Role Logs",
                        "event_embed_channel": "Embedded Role Logs",
                        "modlog_chan": "Mod Logs",
                        "message_log_channel": "Message Edits & Deletion Logs",
                        "ban_channel": "Member Ban Logging",
                        "invite_watch": "Invite Watch"}
            logs = []
            for x, y in logging.items():
                logs.append((log_info[x], y)) if x in log_info else None
            msg = ""
            for key, value in logs:
                msg += f"{key}: <#{value}>\n"
            em.add_field(name="Enabled Logs", value=msg)
        if ret['mute_role_id']:
            role = discord.utils.get(ctx.guild.roles, id=ret['mute_role_id'])
            if role:
                em.add_field(name="Mute Role", value=f"{role.name} ({role.id})")
        if ret['prefix']:
            em.add_field(name="Prefixes", value="\n".join(ret['prefix']))
        if ret['warn_kick'] or ret['warn_ban']:
            msg = ""
            if ret['warn_kick']:
                msg += f"Kick: at {ret['warn_kick']} warns\n"
            if ret['warn_ban']:
                msg += f"Ban: at {ret['warn_ban']}+ warns\n"
            em.add_field(name="Warn Punishments", value=msg)
        await ctx.send(embed=em)

    @commands.group(aliases=['logging'])
    @commands.has_permissions(administrator=True)
    async def log(self, ctx):
        """Setup various compact logging for the server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.has_permissions(administrator=True)
    @log.command(name="join-logs", aliases=['joinlogs'])
    async def setjoinlogs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users join or leave your server
        and sends it to the specified logging channel.

        Compact Logs"""
        guild_config = await self.grab_modconfig(ctx)
        if "join_log_embed_channel" in guild_config:
            return await ctx.send("You can only have one type of logging!")
        if channel == "disable":
            if "join_log_channel" in guild_config:
                guild_config.pop("join_log_channel")
                await ctx.send("Member join and leave logging disabled.")
            else:
                return await ctx.send("Member join and leave logging was never enabled!")
        else:
            guild_config["join_log_channel"] = channel.id
            await ctx.send(f"Member join and leave logging set to {channel.mention} {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.group()
    @commands.has_permissions(administrator=True)
    async def embed(self, ctx):
        """Set up embedded logging."""  # For those who don't like compact logging
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @embed.command(name="setjoinlogs", aliases=['set-join-logs'])
    async def setjoinlogs_embed(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users join or leave your server
        and sends it to the specified logging channel.
        Embedded Logs"""
        guild_config = await self.grab_modconfig(ctx)
        if "join_log_channel" in guild_config:
            return await ctx.send("You can only have one type of logging!")
        if channel == "disable":
            guild_config.pop("join_log_embed_channel")
            await ctx.send("Embedded member join and leave logging disabled.")
        else:
            guild_config["join_log_embed_channel"] = channel.id
            await ctx.send(f"Embedded member join and leave "
                           f"logging set to {channel.mention} {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @embed.command(name="set-role-logs", aliases=['setrolelogs'])
    async def set_event_embed_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users change their
        roles or get theirs changed and sends it to the specified logging channel.

        Embedded Logs"""
        guild_config = await self.grab_modconfig(ctx)
        if "event_channel" in guild_config:
            return await ctx.send("You can only have one type of logging!")
        if channel == "disable":
            guild_config.pop("event_embed_channel")
            await ctx.send("Embedded member role logs have been disabled.")
        else:
            guild_config["event_embed_channel"] = channel.id
            await ctx.send(f"Embedded member role logs have "
                           f"been set to {channel.mention} {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(view_audit_log=True)
    @log.command(name="mod-logs", aliases=['modlogs'])
    async def set_mod_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set where moderation actions should be logged."""
        guild_config = await self.grab_modconfig(ctx)
        if channel == "disable":
            guild_config.pop("modlog_chan")
            await ctx.send("Moderation logs have been disabled.")
        else:
            guild_config["modlog_chan"] = channel.id
            await ctx.send(f"Moderation logs have been set to {channel.mention} {emoji.kurisu}")
        await self.set_modconfig(ctx, guild_config)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="role-logs", aliases=['rolelogs'])
    async def set_event_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users change
        their roles or get theirs changed and sends it to the specified logging channel.

        Compact Logs"""
        guild_config = await self.grab_modconfig(ctx)
        if "event_embed_channel" in guild_config:
            return await ctx.send("You can only have one type of logging!")
        if channel == "disable":
            if "event_channel" in guild_config:
                guild_config.pop("event_channel")
                await ctx.send("Member role logs have been disabled.")
            else:
                return await ctx.send("Member Role logs were never setup!")
        else:
            guild_config["event_channel"] = channel.id
            await ctx.send(f"Member role logs have been set to {channel.mention} {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="message-logs", aliases=['messagelogs'])
    async def setmsglogchannel(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the Message Log Channel"""
        guild_config = await self.grab_modconfig(ctx)
        if channel == "disable":
            if "message_log_channel" in guild_config:
                guild_config.pop("message_log_channel")
                await ctx.send("Message Logging has been disabled")
            else:
                return await ctx.send("Message Logging was never setup!")
        else:
            guild_config["message_log_channel"] = channel.id
            await ctx.send(f"The message log channel has been set to {channel.mention} {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="invite-watch", aliases=['invitewatch'], enabled=False, hidden=True)
    async def set_invite_watch(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the Invite Watching Channel"""
        guild_config = await self.grab_modconfig(ctx)
        if channel == "disable":
            if "invite_watch" in guild_config:
                guild_config.pop("invite_watch")
                await ctx.send("Invite Watching has been disabled")
            else:
                return await ctx.send("Invite Watching was never setup!")
        else:
            guild_config["invite_watch"] = channel.id
            await ctx.send(f"Invite watching will be sent to {channel.mention}. "
                           f"Please note that this doesn't delete "
                           f"invites. {emoji.mayushii}")
        await self.set_modconfig(ctx, guild_config)

    @commands.group(aliases=['mod-role', 'modroles'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def modrole(self, ctx):
        """Configures the guild's mod roles"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.guild_only()
    @modrole.command(name="set", aliases=['add'])
    @commands.has_permissions(administrator=True)
    async def set_mod_role(self, ctx, level: str, *, role: discord.Role):
        """
        Set the various mod roles.

        level: Any of "Helper", "Moderator" or "Admin".
        role: Target role to set.
        """

        if level.lower() not in ["helper", "moderator", "admin"]:
            return await ctx.send("Not a valid level! Level must be "
                                  "one of Helper, Moderator or Admin.")

        query = """INSERT INTO staff_roles
                   VALUES ($1, $2, $3);
                """
        try:
            await self.bot.db.execute(query, ctx.guild.id, role.id, level.lower())
        except asyncpg.UniqueViolationError:
            return await ctx.send("That role is already set as a mod role!")
        await ctx.safe_send(f"Successfully set the {level} rank to "
                            f"the {role.name} role! {emoji.mayushii}")

    @commands.guild_only()
    @modrole.command(name="get", aliases=['list'])
    @commands.has_permissions(manage_guild=True)
    async def get_mod_roles(self, ctx):
        """
        Lists the configured mod roles for this guild.
        """
        query = """SELECT perms, role_id FROM staff_roles WHERE guild_id=$1;"""
        result = await self.bot.db.fetch(query, ctx.guild.id)
        embed = discord.Embed(title="Mod Roles", description="")
        if len(result) == 0:
            embed.description = "No moderation roles are setup!"
        for perms, role_id in result:
            role = discord.utils.get(ctx.guild.roles, id=role_id)
            embed.description += f"{perms}: {role.mention}\n"
        await ctx.send(embed=embed)

    @commands.guild_only()
    @modrole.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def delete_mod_roles(self, ctx, *, role: discord.Role):
        """Deletes one configured mod role."""
        query = """DELETE FROM staff_roles WHERE guild_id=$1 AND role_id=$2"""
        result = await self.bot.db.execute(query, ctx.guild.id, role.id)
        if result == "DELETE 0":
            return await ctx.send("That role is not a configured mod role.")
        await ctx.safe_send(f"Removed {role.name} from the configured mod roles.")

    @commands.guild_only()
    @commands.command(name="set-mute-role", aliases=['setmuterole'])
    @commands.has_permissions(manage_guild=True)
    async def set_mute_role(self, ctx, *, role: discord.Role):
        """Sets the mute role to an existing role"""
        if role.is_default():
            return await ctx.safe_send('Cannot use the @everyone role as the mute role.')
        if role > ctx.me.top_role:
            return await ctx.send('Role is higher than my highest role.')
        query = """INSERT INTO guild_mod_config (guild_id, mute_role_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET mute_role_id = EXCLUDED.mute_role_id;
                """
        await self.bot.db.execute(query, ctx.guild.id, role.id)
        await ctx.safe_send(f"Successfully set the mute role to {role.name}")

    @commands.guild_only()
    @commands.command(name="reset-mute-role",
                      aliases=['deletemuterole', 'delete-mute-role'])
    @commands.has_permissions(manage_guild=True)
    async def delete_mute_role(self, ctx):
        """Deletes the configured mute role."""
        query = """"UPDATE guild_mod_config SET mute_role_id=NULL
                    WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query, ctx.guild.id)
        await ctx.send("Successfully removed the configured mute role.")

    @commands.group(aliases=['autoroles'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx):
        """Setup auto roles for the server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.guild_only()
    @autorole.command(name="set", aliases=['add'])
    @commands.has_permissions(manage_roles=True)
    async def setautoroles(self, ctx, *, role: discord.Role):
        """Sets an auto role for the server"""
        query = """INSERT INTO auto_roles
                VALUES ($1, $2)
                """
        async with self.bot.db.acquire() as con:
            try:
                await con.execute(query, ctx.guild.id, role.id)
            except asyncpg.UniqueViolationError:
                return await ctx.safe_send(f"{role.name} is already set as an auto role.")
        await ctx.safe_send(f"Successfully set {role.name} as an auto role.")

    @commands.guild_only()
    @autorole.command(name='remove')
    @commands.has_permissions(manage_roles=True)
    async def removeautoroles(self, ctx, *, role: discord.Role):
        """Removes a specific auto role that's configured"""
        query = """DELETE FROM auto_roles WHERE guild_id=$1 AND role_id=$2"""
        async with self.bot.db.acquire() as con:
            res = await con.execute(query, ctx.guild.id, role.id)
        if res == "DELETE 0":
            return await ctx.safe_send(f"{role.name} was never set as an autorole!")
        await ctx.safe_send(f"Successfully removed {role.name}")

    @commands.guild_only()
    @autorole.command(name='list', aliases=['show'])
    @commands.has_permissions(manage_roles=True)
    async def showautoroles(self, ctx):
        """Lists all the auto roles this guild has"""
        query = """SELECT role_id FROM auto_roles WHERE guild_id=$1"""
        async with self.bot.db.acquire() as con:
            res = await con.fetch(query, ctx.guild.id)
        if len(res) == 0:
            return await ctx.send("This guild has no auto roles setup!")
        e = discord.Embed(title="Auto Roles", description="", color=0x5f9ff6)
        for role_id in res:
            role = discord.utils.get(ctx.guild.roles, id=role_id[0])
            e.description += f"\N{BULLET} {role.name} (ID: {role.id})\n"
        await ctx.send(embed=e)

    async def add_prefix(self, guild, prefix, connection=None):
        """Adds a prefix to the guild's config"""
        query = """INSERT INTO guild_mod_config (guild_id, prefix)
                   VALUES ($1, $2::text[]) ON CONFLICT (guild_id)
                   DO UPDATE SET
                        prefix = EXCLUDED.prefix;
                """
        if connection is None:
            await self.bot.db.execute(query, guild.id, list(prefix))
        else:
            await connection.execute(query, guild.id, list(prefix))

    async def get_guild_prefixes(self, guild_id: int, connection=None):
        query = """SELECT prefix
                   FROM guild_mod_config
                   WHERE guild_id=$1;"""
        if connection is None:
            ret = await self.bot.db.fetchval(query, guild_id)
        else:
            ret = await connection.fetchval(query, guild_id)
        if ret:
            return ret
        else:
            return []

    async def delete_prefix(self, guild_id, prefix):
        """Deletes a prefix"""
        query = """UPDATE guild_mod_config
                   SET prefix = $1
                   WHERE guild_id = $2;
                """
        if len(prefix) == 0:
            query = """UPDATE guild_mod_config
                       SET prefix = NULL
                       WHERE guild_id = $1;
                    """
            return await self.bot.db.execute(query, guild_id)
        return await self.bot.db.execute(query, prefix, guild_id)

    @commands.group(aliases=['prefixes'])
    @commands.guild_only()
    async def prefix(self, ctx):
        """Manages the server's custom prefixes.

        If called without a subcommand, this will list
        the currently set prefixes for this guild."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="Prefixes",
                                  description="",
                                  color=discord.Color(0xd1486d))
            embed.description += f"\"{ctx.me.mention}\"\n\"l.\"\n"
            for p in await self.get_guild_prefixes(ctx.guild.id):
                embed.description += f"\"{p}\"\n"
            await ctx.send(embed=embed)

    @prefix.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addprefix(self, ctx, prefix: Prefix):
        """Adds a custom prefix.

        To have a prefix with a word (or words), you should quote it and
        end it with a space, e.g. "lightning " to set the prefix
        to "lightning ". This is because Discord removes spaces when sending
        messages so the spaces are not preserved.

        In order to use this command, you must have Manage Server
        permission to use this command."""
        prefixes = await self.get_guild_prefixes(ctx.guild.id)
        if len(prefixes) < 5:
            if prefix in prefixes:
                return await ctx.send("That prefix is already registered!")
            prefixes.append(prefix)
            await self.add_prefix(ctx.guild, prefixes)
            if ctx.guild.id in self.bot.prefixes:
                self.bot.prefixes[ctx.guild.id].append(prefix)
            else:
                self.bot.prefixes[ctx.guild.id] = prefixes
        else:
            return await ctx.send("You can only have 5 custom prefixes per guild! Please remove one.")
        await ctx.send(f"Added `{prefix}`")

    @prefix.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def rmprefix(self, ctx, prefix: Prefix):
        """Removes a custom prefix.

        The inverse of the prefix add command.

        To remove word/multi-word prefixes, you need to quote it.

        Example: `l.prefix remove "lightning "` removes the "lightning " prefix.

        In order to use this command, you must have Manage Server
        permission to use this command.
        """
        # Bc I'm partially lazy
        prefixes = await self.get_guild_prefixes(ctx.guild.id)
        if prefix in prefixes:
            prefixes.remove(prefix)
            await self.delete_prefix(ctx.guild.id, prefixes)
            if ctx.guild.id in self.bot.prefixes:
                self.bot.prefixes[ctx.guild.id].remove(prefix)
        else:
            return await ctx.send(f"{prefix} was never added as a custom prefix.")
        await ctx.send(f"Removed `{prefix}`")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        query = """SELECT role_id FROM auto_roles WHERE guild_id=$1"""
        async with self.bot.db.acquire() as con:
            res = await con.fetch(query, member.guild.id)
        roles = [discord.utils.get(member.guild.roles, id=role_id[0]) for role_id in res]
        try:
            await member.add_roles(*roles, reason="Auto Roles")
        except Exception:
            pass


def setup(bot):
    bot.add_cog(Configuration(bot))
