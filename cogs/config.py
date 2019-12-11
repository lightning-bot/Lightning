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


import asyncio
import json
from typing import Union

import asyncpg
import discord
from discord.ext import commands

import resources.botemojis as emoji
from utils.converters import ValidCommandName
from utils.errors import LightningError
from utils.paginator import Pages
from utils.database import GuildModConfig
from utils.checks import has_guild_permissions


class Prefix(commands.Converter):
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
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
        ret = await self.bot.db.fetchval(query, ctx.guild.id)
        if ret:
            guild_config = json.loads(ret)
        else:
            guild_config = {}

        return guild_config

    async def get_mod_config(self, ctx):
        query = """SELECT * FROM guild_mod_config WHERE guild_id=$1"""
        ret = await self.bot.db.fetchrow(query, ctx.guild.id)
        if not ret:
            return None
        return GuildModConfig(ret)

    async def set_modconfig(self, ctx, to_dump):
        """Sets a mod config for a guild and
        dumps what's passed in to_dump. """
        query = """INSERT INTO guild_mod_config (guild_id, log_channels)
                   VALUES ($1, $2::jsonb)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET log_channels = EXCLUDED.log_channels;"""
        await self.bot.db.execute(query, ctx.guild.id,
                                  json.dumps(to_dump))
        mod = self.bot.get_cog('Mod')
        mod.get_mod_config.invalidate(mod, ctx.guild.id)

    @commands.command(name="settings")
    @commands.has_permissions(manage_guild=True)
    async def view_guild_settings(self, ctx):
        """Views the guild's settings for the bot"""
        em = discord.Embed(title=f"Settings for {ctx.guild.name}", color=0xf74b06)
        ret = await self.get_mod_config(ctx)
        if not ret:
            return await ctx.send("No settings found!")
        if ret.log_channels:
            logging = json.loads(ret.log_channels)
            log_info = {"member_join": "Member Join Logging",
                        "role_change": "Member Role Change Logging",
                        "modlog_chan": "Mod Logging",
                        "member_leave": "Member Leave Logging",
                        "invite_watch": "Invite Watch",
                        "bot_add": "Bot Add"}
            logs = []
            for x, y in logging.items():
                logs.append((log_info[x], y)) if x in log_info else None
            msg = ""
            for key, value in logs:
                msg += f"{key}: <#{value}>\n"
            if msg:
                em.add_field(name="Enabled Logs", value=msg)
        if ret.mute_role_id:
            role = discord.utils.get(ctx.guild.roles, id=ret.mute_role_id)
            if role:
                em.add_field(name="Mute Role", value=f"{role.name} ({role.id})")
        if ret.warn_kick or ret.warn_ban:
            msg = ""
            if ret.warn_kick:
                msg += f"Kick: at {ret.warn_kick} warns\n"
            if ret.warn_ban:
                msg += f"Ban: at {ret.warn_ban}+ warns\n"
            em.add_field(name="Warn Punishments", value=msg)
        if ret.log_format:
            em.add_field(name="Log Format", value=f"{ret.log_format.title()}", inline=False)
        await ctx.send(embed=em)

    @commands.group(aliases=['logging'], hidden=True)
    @commands.has_permissions(administrator=True)
    async def log(self, ctx):
        """Setup various compact logging for the server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def add_reacts(self, message, reacts):
        reacts.append("\N{BLACK SQUARE FOR STOP}")
        for r in reacts:
            await message.add_reaction(r)

    async def log_all_in_one(self, ctx, channel):
        values = {"role_change": channel.id,
                  "modlog_chan": channel.id,
                  "member_join": channel.id,
                  "member_leave": channel.id,
                  "bot_add": channel.id}
        await self.set_modconfig(ctx, values)

    async def remove_channel_log(self, ctx, channel):
        ret = await self.grab_modconfig(ctx)
        keys = list(ret.keys())
        for v in keys:
            if ret[v] == channel.id:
                ret.pop(v)
        await self.set_modconfig(ctx, ret)

    async def change_log_format(self, guild_id, log_format):
        query = """INSERT INTO guild_mod_config (guild_id, log_format)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET log_format = EXCLUDED.log_format;
                """
        await self.bot.db.execute(query, guild_id, log_format)
        mod = self.bot.get_cog('Mod')
        mod.get_mod_config.invalidate(mod, guild_id)

    async def edit_and_continue(self, message, new_content, clear_reacts=True, **kwargs):
        if clear_reacts:
            await message.clear_reactions()
        msg = await message.edit(content=new_content)
        if clear_reacts:
            if "reactions" in kwargs:
                reacts = kwargs.pop('reactions')
                reacts.append("\N{BLACK SQUARE FOR STOP}")
                for r in reacts:
                    await message.add_reaction(r)
        return msg

    @commands.command()
    @commands.bot_has_permissions(manage_messages=True, view_audit_log=True,
                                  add_reactions=True, send_messages=True)
    @has_guild_permissions(manage_guild=True)
    async def setup(self, ctx, *, channel: discord.TextChannel = None):
        """Sets up logging for the server.

        This handles changing the log format, removing logging from a channel,
        and setting up logging for a channel.

        In order to use this command, you need Manage Server permission.
        """
        if not channel:
            channel = ctx.channel
        initalemojis = ["\N{LEDGER}", "\N{OPEN BOOK}", "\N{CLOSED BOOK}", "\N{NOTEBOOK}"]

        msg = await ctx.send(f"React with {initalemojis[0]} to log everything to {channel.mention}, "
                             f"react with {initalemojis[1]} to setup specific logging, "
                             f"or react with {initalemojis[2]} to remove logging "
                             f"from {channel.mention}. To change the mod logging format, "
                             f"react with {initalemojis[3]}."
                             " If you want to cancel setup, react with "
                             "\N{BLACK SQUARE FOR STOP} to cancel.")
        await self.add_reacts(msg, initalemojis)

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in initalemojis
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long to respond.')
        if str(reaction) == "\N{BLACK SQUARE FOR STOP}":
            return await ctx.send("Canceled.")
        elif str(reaction) == initalemojis[0]:
            await self.log_all_in_one(ctx, channel)
            return await ctx.send(f"Successfully setup {channel.mention} as a logging channel.")
        elif str(reaction) == initalemojis[2]:
            await self.remove_channel_log(ctx, channel)
            # TODO: Checks
            return await ctx.send(f"Successfully removed logging from {channel.mention}.")
        elif str(reaction) == initalemojis[3]:
            logemojis = ["<:kurisu:644378407009910794>", "<:lightning:634193020950020097>"]
            logformats = [f'{logemojis[0]} for Kurisu format',
                          f'{logemojis[1]} for Lightning format']
            msg = await self.edit_and_continue(msg, f"React with {' or '.join(logformats)}."
                                               " If you want to cancel setup, react with "
                                               "\N{BLACK SQUARE FOR STOP} to cancel.",
                                               reactions=logemojis)

            def checklog(reaction, user):
                return user == ctx.author and str(reaction.emoji) in logemojis
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=checklog)
            except asyncio.TimeoutError:
                return await ctx.send('You took too long to respond.')
            if str(reaction) == "\N{BLACK SQUARE FOR STOP}":
                return await ctx.send("Canceled.")
            elif str(reaction) in logemojis:
                ext = {f"{logemojis[0]}": "kurisu", f"{logemojis[1]}": "lightning"}
                await self.change_log_format(ctx.guild.id, ext[str(reaction)])
                return await ctx.send("Successfully changed log format!")
        elif str(reaction) == initalemojis[1]:
            eventcontent = "​Send the number of each event "\
                           "you want to log in a single message "\
                           "(space separated, \"1 3 5\"):\n"\
                           "mod_logging: 1, member_join: 2, member_leave: 3,"\
                           " role_change: 4, bot_add: 5."\
                           " **To cancel, type `cancel`**"
            await self.edit_and_continue(msg, eventcontent, clear_reacts=True)

            def checkmsg(msg):
                return msg.channel == ctx.message.channel and msg.author == ctx.message.author
            try:
                message = await self.bot.wait_for('message', timeout=60.0, check=checkmsg)
            except asyncio.TimeoutError:
                return await ctx.send('You took too long to respond.')
            if message.content == "cancel":
                return await ctx.send("Cancelled.")
            message = message.content.split()
            entries = {"1": "modlog_chan", "2": "member_join",
                       "3": "member_leave", "4": "role_change",
                       "5": "bot_add"}
            tempval = 0
            for i in message:
                if i in list(entries.keys()):
                    tempval = 1
                    ret = await self.grab_modconfig(ctx)
                    ret[entries[i]] = channel.id
                    await self.set_modconfig(ctx, ret)
            if tempval:
                await ctx.send(f"Successfully set up logging for {channel.mention}!")
            else:
                await ctx.send("Unable to determine what logging you wanted setup!")

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

    @commands.is_owner()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @log.command(name="aio", aliases=['allinone'], hidden=True)
    async def log_aio(self, ctx):
        """Creates 3 channels for logging."""
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                      manage_channels=True),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    manage_channels=True, manage_messages=True)
        }
        logcategory = await ctx.guild.create_category('Logs', overwrites=overwrites)
        modlogchannel = await ctx.guild.create_text_channel('mod-logs', category=logcategory)
        memberevtlog = await ctx.guild.create_text_channel('member-event-logs',
                                                           category=logcategory)
        guild_config = await self.grab_modconfig(ctx)
        if "event_embed_channel" in guild_config:
            guild_config.pop("event_embed_channel")
        guild_config['modlog_chan'] = modlogchannel.id
        guild_config['event_channel'] = memberevtlog.id
        await self.set_modconfig(ctx, guild_config)
        await ctx.send(f"Successfully created 3 log channels")

    @log_aio.error
    async def log_aio_err(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            return await ctx.send("This is a testing command and you cannot use "
                                  "it at this time.")

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

    async def add_prefix(self, guild, prefix, connection=None):
        """Adds a prefix to the guild's config"""
        query = """INSERT INTO guild_config (guild_id, prefix)
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
                   FROM guild_config
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
        query = """UPDATE guild_config
                   SET prefix = $1
                   WHERE guild_id = $2;
                """
        if len(prefix) == 0:
            query = """UPDATE guild_config
                       SET prefix = NULL
                       WHERE guild_id = $1;
                    """
            return await self.bot.db.execute(query, guild_id)
        return await self.bot.db.execute(query, prefix, guild_id)

    @commands.group(aliases=['prefixes'], invoke_without_command=True)
    @commands.guild_only()
    async def prefix(self, ctx):
        """Manages the server's custom prefixes.

        If called without a subcommand, this will list
        the currently set prefixes for this guild."""
        embed = discord.Embed(title="Prefixes",
                              description="",
                              color=discord.Color(0xd1486d))
        embed.description += f"\"{ctx.me.mention}\"\n"
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
        query = """SELECT autorole FROM guild_config WHERE guild_id=$1"""
        res = await self.bot.db.fetchval(query, member.guild.id)
        if res:
            role = discord.utils.get(member.guild.roles, id=res)
            try:
                await member.add_roles(role, reason="Automatic Role")
            except Exception:
                pass

    def is_command_blocked(self, ctx, ret):
        if not ret:
            return False
        if ret['channel_id'] is None:
            if ret['whitelist']:
                return False
            else:
                return True
        else:
            if ctx.channel.id == ret['channel_id']:
                if ret['whitelist']:
                    return False
                else:
                    return True

    async def get_command_blacklists(self, ctx):
        query = "SELECT channel_id, whitelist FROM command_plonks WHERE guild_id=$1 AND name=$2;"
        ret = await self.bot.db.fetchrow(query, ctx.guild.id, ctx.command.qualified_name)
        return ret

    async def bot_check(self, ctx):
        if ctx.guild is None:
            return True
        ret = await self.get_command_blacklists(ctx)
        is_owner = await ctx.bot.is_owner(ctx.author)
        if is_owner:
            return True
        if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.manage_guild:
            return True
        return not self.is_command_blocked(ctx, ret)

    @commands.group()
    @has_guild_permissions(manage_guild=True)
    async def config(self, ctx):
        """Manages most of the configuration for the bot.

        This manages autorole configuration, muterole configuration,
        and command plonking configuration"""
        # TODO: Add Autorole under config group
        if ctx.invoked_subcommand is None:
            await ctx.send_help('config')

    @config.group(invoke_without_command=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        """Manages the guild's autorole"""
        await ctx.send_help('config autorole')

    @autorole.command(name="set", aliases=['add'])
    @commands.bot_has_permissions(manage_roles=True)
    @commands.has_permissions(manage_roles=True)
    async def setautoroles(self, ctx, *, role: discord.Role):
        """Sets an auto role for the server"""
        query = """INSERT INTO guild_config (guild_id, autorole)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET autorole = EXCLUDED.autorole;
                """
        if role > ctx.me.top_role:
            return await ctx.send('Role is higher than my highest role.')
        await self.bot.db.execute(query, ctx.guild.id, role.id)
        await ctx.safe_send(f"Successfully set {role.name} as an auto role.")

    @autorole.command(name='remove')
    @commands.has_permissions(manage_roles=True)
    async def removeautoroles(self, ctx):
        """Removes the auto role that's configured"""
        query = """UPDATE guild_config SET autorole=NULL
                   WHERE guild_id=$1;"""
        res = await self.bot.db.execute(query, ctx.guild.id)
        if res == "UPDATE 0":
            return await ctx.safe_send("This guild never had an autorole setup!")
        await ctx.safe_send("Successfully removed the guild's autorole")

    @config.group(aliases=['mute-role'], invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def muterole(self, ctx, *, role: discord.Role = None):
        """Handles mute role configuration"""
        if not role:
            ret = await self.get_mod_config(ctx)
            if not ret and ret.mute_role(ctx):
                return await ctx.send("There is no mute role setup!")
            else:
                mute = ret.mute_role(ctx)
                if mute:
                    return await ctx.safe_send(f"The current mute role is set to {mute.name} ({mute.id})")
                else:
                    return await ctx.send("There is no mute role setup!")
        if role.is_default():
            return await ctx.send('You cannot use the @\u200beveryone role.')
        if role > ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send('This role is higher than your highest role.')
        if role > ctx.me.top_role:
            return await ctx.send('This role is higher than my highest role.')
        query = """INSERT INTO guild_mod_config (guild_id, mute_role_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET mute_role_id = EXCLUDED.mute_role_id;
                """
        await self.bot.db.execute(query, ctx.guild.id, role.id)
        mod = self.bot.get_cog('Mod')
        mod.get_mod_config.invalidate(mod, ctx.guild.id)
        await ctx.safe_send(f"Successfully set the mute role to {role.name}")

    @muterole.command(name="reset",
                      aliases=['delete', 'remove'])
    @has_guild_permissions(manage_guild=True)
    async def delete_mute_role(self, ctx):
        """Deletes the configured mute role."""
        query = """UPDATE guild_mod_config SET mute_role_id=NULL
                    WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query, ctx.guild.id)
        mod = self.bot.get_cog('Mod')
        mod.get_mod_config.invalidate(mod, ctx.guild.id)
        await ctx.send("Successfully removed the configured mute role.")

    async def update_mute_role_permissions(self, role, guild, author):
        success = 0
        failure = 0
        skipped = 0
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).manage_roles:
                overwrite = channel.overwrites_for(role)
                if overwrite.send_messages is False and overwrite.add_reactions is False:
                    skipped += 1
                    continue
                overwrite.send_messages = False
                overwrite.add_reactions = False
                try:
                    await channel.set_permissions(role, overwrite=overwrite,
                                                  reason=f'Action done by {author} (ID: {author.id})')
                except discord.HTTPException:
                    failure += 1
                else:
                    success += 1
            else:
                skipped += 1
        return success, failure, skipped

    @muterole.command(name="update")
    @has_guild_permissions(manage_guild=True)
    async def mute_role_perm_update(self, ctx):
        """Updates the permission overwrites of the mute role.

        This sets the permissions to Send Messages and Add Reactions as False
        on every text channel that the bot can set permissions for."""
        config = await self.get_mod_config(ctx)
        if config is None or config.mute_role(ctx) is None:
            return await ctx.safe_send("No mute role is currently set. You can set one with"
                                       f"`{ctx.prefix}config muterole <role>`.")
        success, f, skip = await self.update_mute_role_permissions(config.mute_role(ctx),
                                                                   ctx.guild, ctx.author)
        await ctx.send(f"Updated {success} channel overrides successfully, {f} channels failed, and "
                       f"{skip} channels were skipped.")

    @config.group(invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    async def server(self, ctx):
        """Handles the server-specific command permissions."""
        await ctx.send_help('config server')

    # Yes, I based this off R.Danny. Channel plonking is in the works.
    async def command_toggle(self, guild_id, channel_id, command_name, *, whitelist=True):
        if not channel_id:
            check = 'channel_id IS NULL'
            args = (guild_id, command_name)
        else:
            check = 'channel_id=$3'
            args = (guild_id, command_name, channel_id)
        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                query = f"DELETE FROM command_plonks WHERE guild_id=$1 AND name=$2 AND {check}"
                await connection.execute(query, *args)
                query = """INSERT INTO command_plonks (guild_id, channel_id, name, whitelist)
                           VALUES ($1, $2, $3, $4);
                        """
                try:
                    await connection.execute(query, guild_id, channel_id, command_name, whitelist)
                except asyncpg.UniqueViolationError:
                    raise LightningError(f"{emoji.x} This command is already disabled!")

    @server.command(name="disable")
    @has_guild_permissions(manage_guild=True)
    async def guild_disable(self, ctx, *, command: ValidCommandName):
        """Disables a command server wide"""
        try:
            await self.command_toggle(ctx.guild.id, None, command, whitelist=False)
        except LightningError:
            return
        else:
            await ctx.send(f"{emoji.checkmark} Command successfully disabled server-wide.")

    @server.command(name="enable")
    @has_guild_permissions(manage_guild=True)
    async def guild_enable(self, ctx, *, command: ValidCommandName):
        """Enables a command for the guild"""
        try:
            await self.command_toggle(ctx.guild.id, None, command, whitelist=True)
        except LightningError:
            return
        else:
            await ctx.send(f"{emoji.checkmark} Command successfully enabled server-wide.")

    @server.command(name="show", aliases=['list'])
    async def guild_disabled(self, ctx):
        """Shows all commands currently disabled throughout the whole server"""
        query = """SELECT name FROM command_plonks
                   WHERE guild_id=$1 AND channel_id IS NULL AND whitelist='false';
                """
        records = await self.bot.db.fetch(query, ctx.guild.id)
        if not records:
            return await ctx.send("All commands are currently enabled server-wide!")
        cmdsblacklisted = []
        for name in records:
            cmdsblacklisted.append(name['name'])
        p = Pages(ctx, entries=cmdsblacklisted)
        p.embed.title = "Commands Currently Blacklisted Server-Wide"
        await p.paginate()

    # @config.group(invoke_without_command=True)
    # async def log(self, ctx):
    # @config.group(invoke_without_command=True)
    # async def channel(self, ctx):
    #    """Handles the channel-specific command permissions."""
    #    await ctx.send_help('config channel')


def setup(bot):
    bot.add_cog(Configuration(bot))
