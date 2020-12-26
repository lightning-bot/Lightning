"""
Lightning.py - A personal Discord bot
Copyright (C) 2020 - LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import contextlib
import re
from typing import Optional, Union

import discord
from discord.ext import commands, menus

from lightning import (CommandLevel, LightningBot, LightningCog,
                       LightningContext, cache)
from lightning import command as lcommand
from lightning import group as lgroup
from lightning.converters import (Prefix, Role, ValidCommandName,
                                  convert_to_level, convert_to_level_value)
from lightning.formatters import plural
from lightning.models import ConfigFlags, GuildModConfig
from lightning.utils.checks import has_guild_permissions
from lightning.utils.helpers import Emoji
from lightning.utils.paginator import SessionMenu

LOG_FORMAT_D = {Emoji.numbers[0]: 'emoji', Emoji.numbers[1]: 'minimal with timestamp',
                Emoji.numbers[2]: 'minimal without timestamp', Emoji.numbers[3]: 'embed'}
LOGGING_TYPES = {"1": "WARN", "2": "KICK", "3": "BAN", "4": "MUTE",
                 "5": "UNMUTE", "6": "MEMBER_JOIN", "7": "MEMBER_LEAVE"}


class SetupMenu(SessionMenu):
    def __init__(self, channel, **kwargs):
        super().__init__(**kwargs)
        self.log_channel = channel
        self._emoji_list = ["\N{LEDGER}", "\N{OPEN BOOK}", "\N{CLOSED BOOK}", "\N{NOTEBOOK}"]

    async def send_initial_message(self, ctx, channel):
        emoji_init = self._emoji_list
        content = f"React with {emoji_init[0]} to log everything to {self.log_channel.mention}, "\
                  f"react with {emoji_init[1]} to setup specific logging, "\
                  f"or react with {emoji_init[2]} to remove logging "\
                  f"from {self.log_channel.mention}. To change the mod logging format, "\
                  f"react with {emoji_init[3]}."\
                  "\n\nIf you want to cancel setup, react with "\
                  "\N{BLACK SQUARE FOR STOP}."
        return await channel.send(content)

    async def remove_channel_log(self, *, connection=None) -> str:
        """Removes logging from a channel

        connection : None, Optional
            Optional database connection to use

        Returns
        -------
        str
            The result of the query
        """
        connection = connection if connection else self.bot.pool
        query = """DELETE FROM logging WHERE guild_id=$1 AND channel_id=$2;"""
        return await connection.execute(query, self.ctx.guild.id, self.log_channel.id)

    async def log_all_in_one(self, guild_id: int, channel_id: int, *, connection=None) -> None:
        connection = connection or self.bot.pool
        allevents = list(LOGGING_TYPES.values())
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)"""
        # TODO: Tell the user we are already logging x events
        await connection.execute(query, guild_id, channel_id, allevents)

    @menus.button('\N{LEDGER}')
    async def log_everything(self, payload) -> None:
        await self.log_all_in_one(self.ctx.guild.id, self.log_channel.id)
        await self.ctx.send(f"Successfully setup logging for {self.log_channel.mention}")
        self.stop()

    async def _setup_logging(self, payload: discord.Message):
        match = re.fullmatch(r'^[\s\d]+$', payload.content)
        group = match.group().split()
        if not group:
            await self.ctx.send("Unable to determine what logging to setup")
            return self.stop()

        toggled = []
        for char in group:
            try:
                toggled.append(LOGGING_TYPES[char])
            except KeyError:
                continue

        if toggled:
            query = "SELECT types FROM logging WHERE guild_id=$1 AND channel_id=$2;"
            types = await self.bot.pool.fetchval(query, self.ctx.guild.id, self.log_channel.id) or []
            types.extend(toggled)
            query = """INSERT INTO logging (guild_id, channel_id, types)
                       VALUES ($1, $2, $3::text[])
                       ON CONFLICT (channel_id)
                       DO UPDATE SET types = EXCLUDED.types;"""
            await self.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, set(types))
            await self.ctx.send(f"Successfully set up logging for {self.log_channel.mention}! ({', '.join(toggled)})")
            self.stop()
        else:
            await self.ctx.send("Unable to determine what logging you wanted setup!")
            self.stop()

    @menus.button('\N{OPEN BOOK}')
    async def specific_logging(self, payload) -> None:
        await self.clear_buttons(react=True)

        content = "​Send the number of each event "\
                  "you want to log in a single message "\
                  "(space separated, \"1 3 5\"):\n"
        items = []
        for x, y in LOGGING_TYPES.items():
            items.append(f"{y.lower()}: {x}")
        content += ', '.join(items) + "\n\n**To cancel, send 0**"
        await self.message.edit(content=content)

        def check(m):
            return m.author.id == self.ctx.author.id and self.ctx.channel.id == m.channel.id

        await self.add_button(menus.Button('⏹', self.quit), react=True)
        self.add_command(check, self._setup_logging)

    @menus.button('\N{CLOSED BOOK}')
    async def remove_logging(self, payload) -> None:
        resp = await self.remove_channel_log()
        await self.ctx.send(f"Removed logging from {self.log_channel.mention}!")
        if resp != 0:
            # Invalidate cache if channel was a logging channel
            c = cache.registry.get("mod_config")
            await c.invalidate(str(self.ctx.guild.id))
        self.stop()

    @menus.button("\N{NOTEBOOK}")
    async def change_format(self, payload) -> None:
        await self.clear_buttons(react=True)

        logformats = [f'{Emoji.numbers[0]} for Emoji format',
                      f'{Emoji.numbers[1]} for Minimalistic with Timestamp format']
        content = f"React with {' or '.join(logformats)}.\n\nIf you want to cancel setup, react with " \
                  "\N{BLACK SQUARE FOR STOP} to cancel."
        await self.message.edit(content=content)

        for emoji in LOG_FORMAT_D:
            await self.add_button(menus.Button(emoji, self.process_payload), react=True)

        await self.add_button(menus.Button('⏹', self.quit), react=True)

    @menus.button('⏹')
    async def quit(self, payload) -> None:
        await self.ctx.send("Cancelled")
        self.stop()

    async def process_payload(self, payload):
        """Changes the log format based on the payload"""
        query = """UPDATE logging SET format=$1 WHERE guild_id=$2 and channel_id=$3;"""
        result = await self.bot.pool.execute(query, LOG_FORMAT_D[str(payload.emoji)], self.ctx.guild.id,
                                             self.log_channel.id)
        if result == "UPDATE 0":
            await self.ctx.send(f"{self.log_channel.mention} is not setup as a logging channel!")
            return self.stop()

        c = cache.registry.get("mod_config")
        await c.invalidate(str(self.ctx.guild.id))
        await self.ctx.send("Successfully changed log format")
        self.stop()

    async def start(self, *args, **kwargs) -> None:
        await super().start(*args, **kwargs)


class ConfigViewerMenu(menus.Menu):
    def give_help(self) -> discord.Embed:
        messages = ['Welcome to the interactive config viewer!\n']
        messages.append('This interactively allows you to see configuration settings of the bot by navigating with '
                        'reactions. They are as follows:\n')
        for emoji, button in self.buttons.items():
            messages.append(f'{str(emoji)} {button.action.__doc__}')

        embed = discord.Embed(color=discord.Color.blurple())
        embed.description = '\n'.join(messages)
        return embed

    async def send_initial_message(self, ctx: LightningContext, channel):
        # Help page
        return await channel.send(embed=self.give_help())

    @menus.button('\N{CLOSED BOOK}')
    async def generic_stuff(self, payload) -> None:
        """Displays prefix and generic bot settings"""
        record = await self.bot.get_guild_bot_config(self.ctx.guild.id)
        embed = discord.Embed(color=discord.Color.red())
        embed.add_field(name="Prefixes", value='\n'.join(record.prefixes))

        if record.flags:
            embed.add_field(name="InvokeDelete", value="Enabled" if record.flags.invoke_delete else "Disabled",
                            inline=False)
            embed.add_field(name="Role Reapply", value="Enabled" if record.flags.role_reapply else "Disabled",
                            inline=False)

        if record.autorole:
            role = self.ctx.guild.get_role(record.autorole)
            if role:
                embed.add_field(name="Autorole", value=f"{role.name} (ID: {role.id})")

        await self.message.edit(embed=embed)

    @menus.button('\N{WARNING SIGN}')
    async def moderation(self, payload) -> None:
        """Shows moderation related settings"""
        obj = await self.ctx.cog.get_mod_config(self.ctx)
        embed = discord.Embed(color=discord.Color.gold())

        # Mute Role stuff
        if obj.mute_role_id is not None:
            role = discord.utils.get(self.ctx.guild.roles, id=obj.mute_role_id)
            if role is not None:
                embed.add_field(name="Permanent Mute Role", value=f"{role.name} (ID: {role.id})")

        if obj.temp_mute_role_id:
            role = discord.utils.get(self.ctx.guild.roles, id=obj.temp_mute_role_id)
            if role is not None:
                embed.add_field(name="Temporary Mute Role", value=f"{role.name} (ID: {role.id})")

        # Warn Thresholds
        if obj.warn_kick or obj.warn_ban:
            msg = ""
            if obj.warn_kick:
                msg += f"Kick: at {obj.warn_kick} warns\n"
            if obj.warn_ban:
                msg += f"Ban: at {obj.warn_ban}+ warns\n"
            embed.add_field(name="Warn Thresholds", value=msg)

        await self.message.edit(embed=embed)

    @menus.button('\N{INFORMATION SOURCE}\ufe0f')
    async def show_help(self, payload) -> None:
        """Shows help"""
        await self.message.edit(embed=self.give_help())


Features = {"role saver": (ConfigFlags.role_reapply, "Now saving member roles.", "No longer saving member roles."),
            "invoke delete": (ConfigFlags.invoke_delete, "Now deleting successful command invocation messages",
                              "No longer deleting successful command invocation messages")}


def convert_to_feature(argument):
    if argument.lower() in Features.keys():
        return Features[argument.lower()]
    else:
        raise commands.BadArgument(f"\"{argument}\" is not a valid feature flag.")


class Configuration(LightningCog):
    """Server configuration commands"""

    async def cog_check(self, ctx) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def get_mod_config(self, ctx, *, connection=None) -> Optional[GuildModConfig]:
        connection = connection if connection else self.bot.pool
        query = """SELECT * FROM guild_mod_config WHERE guild_id=$1"""
        ret = await connection.fetchrow(query, ctx.guild.id)
        if not ret:
            return None
        return GuildModConfig(ret)

    async def invalidate_config(self, ctx: LightningContext, *, config_name="mod_config") -> bool:
        """Function to reduce duplication for invalidating a cached guild mod config"""
        c = cache.registry.get(config_name)
        return await c.invalidate(str(ctx.guild.id))

    @lcommand(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def settings(self, ctx):
        menu = ConfigViewerMenu(timeout=60.0, clear_reactions_after=True)
        await menu.start(ctx)

    async def remove_config_key(self, guild_id: int, key: str, *, column='guild_config') -> str:
        query = f"UPDATE {column} SET {key} = NULL WHERE guild_id=$1;"
        return await self.bot.pool.execute(query, guild_id)

    @lgroup(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def config(self, ctx: LightningContext) -> None:
        """Manages most of the configuration for the bot.

        Manages:
          - Mute role
          - Logging
          - Prefixes
          - Command Overrides
          - Feature Flags
          - Levels"""
        await ctx.send_help('config')

    async def add_prefix(self, guild: discord.Guild, prefix: list, *, connection=None) -> None:
        """Adds a prefix to the guild's config"""
        query = """INSERT INTO guild_config (guild_id, prefix)
                   VALUES ($1, $2::text[]) ON CONFLICT (guild_id)
                   DO UPDATE SET
                        prefix = EXCLUDED.prefix;
                """
        connection = connection or self.bot.pool
        await connection.execute(query, guild.id, list(prefix))

    async def get_guild_prefixes(self, guild_id: int, connection=None) -> list:
        connection = connection or self.bot.pool
        query = """SELECT prefix
                   FROM guild_config
                   WHERE guild_id=$1;"""
        val = await connection.fetchval(query, guild_id)
        return val or []

    async def delete_prefix(self, guild_id: int, prefixes: list) -> str:
        """Deletes a prefix"""
        if len(prefixes) == 0:
            query = "UPDATE guild_config SET prefix = NULL WHERE guild_id = $1;"
            args = [guild_id]
        else:
            query = "UPDATE guild_config SET prefix = $1 WHERE guild_id = $2;"
            args = [prefixes, guild_id]

        return await self.bot.pool.execute(query, *args)

    @config.group(aliases=['prefixes'], invoke_without_command=True)
    async def prefix(self, ctx: LightningContext) -> None:
        """Manages the server's custom prefixes.

        If called without a subcommand, this will list the currently set prefixes for this server."""
        embed = discord.Embed(title="Prefixes",
                              description="",
                              color=discord.Color(0xd1486d))
        embed.description += f"\"{ctx.me.mention}\"\n"
        for p in await self.get_guild_prefixes(ctx.guild.id):
            embed.description += f"\"{p}\"\n"
        await ctx.send(embed=embed)

    @prefix.command(name="add", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def addprefix(self, ctx: LightningContext, prefix: Prefix) -> None:
        """Adds a custom prefix.

        To have a prefix with a word (or words), you should quote it and \
        end it with a space, e.g. "lightning " to set the prefix \
        to "lightning ". This is because Discord removes spaces when sending \
        messages so the spaces are not preserved."""
        prefixes = await self.get_guild_prefixes(ctx.guild.id)
        if len(prefixes) >= 5:
            await ctx.send("You can only have 5 custom prefixes per guild! Please remove one.")
            return

        if prefix in prefixes:
            await ctx.send("That prefix is already registered!")
            return

        prefixes.append(prefix)
        await self.add_prefix(ctx.guild, prefixes)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)

        await ctx.send(f"Added `{prefix}`")

    @prefix.command(name="remove", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def rmprefix(self, ctx: LightningContext, prefix: Prefix) -> None:
        """Removes a custom prefix.

        To remove word/multi-word prefixes, you need to quote it.

        Example: `.prefix remove "lightning "` removes the "lightning " prefix.
        """
        prefixes = await self.get_guild_prefixes(ctx.guild.id)
        if prefix not in prefixes:
            await ctx.send(f"{prefix} was never added as a custom prefix.")
            return

        prefixes.remove(prefix)
        await self.delete_prefix(ctx.guild.id, prefixes)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Removed `{prefix}`")

    async def add_config_key(self, guild_id, key, value, *, column="guild_config") -> str:
        query = f"""INSERT INTO {column} (guild_id, {key})
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET {key} = EXCLUDED.{key};"""
        return await self.bot.pool.execute(query, guild_id, value)

    @config.command(level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_messages=True, view_audit_log=True, send_messages=True)
    @has_guild_permissions(manage_guild=True)
    async def logging(self, ctx, *, channel: discord.TextChannel = commands.default.CurrentChannel):
        """Sets up logging for the server.

        This handles changing the log format for the server, removing logging from a channel, and setting up \
        logging for a channel."""
        _session = SetupMenu(channel, timeout=60, clear_reactions_after=True)
        await _session.start(ctx, wait=True)

    async def toggle_feature_flag(self, guild_id: int, flag: ConfigFlags) -> ConfigFlags:
        """Toggles a feature flag for a guild

        Parameters
        ----------
        guild_id : int
            The ID of the server
        flag : ConfigFlags
            The flag that is being toggled.

        Returns
        -------
        ConfigFlags
            Returns the newly created flags.
        """
        record = await self.bot.get_guild_bot_config(guild_id)
        toggle = record.flags - flag if record.flags.invoke_delete is True else \
            record.flags | flag
        await self.add_config_key(guild_id, "flags", int(toggle))
        await self.bot.get_guild_bot_config.invalidate(guild_id)
        return toggle

    @config.command(level=CommandLevel.Admin)
    @commands.bot_has_guild_permissions(manage_messages=True)
    @has_guild_permissions(manage_guild=True)
    async def toggle(self, ctx: LightningContext, *, feature: convert_to_feature) -> None:
        """Toggles a feature flag"""
        flag, piece_yes, piece_no = feature
        toggle = await self.toggle_feature_flag(ctx.guild.id, flag)

        if flag in toggle:
            piece = piece_yes
        else:
            piece = piece_no

        await ctx.send(piece)

    @LightningCog.listener()
    async def on_command_completion(self, ctx: LightningContext) -> None:
        if ctx.guild is None:
            return

        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record.flags.invoke_delete:
            return

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            # Toggle it off
            await self.add_config_key(ctx.guild.id, "invoke_delete", False)
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
            return
        except discord.NotFound:
            return

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def autorole(self, ctx: LightningContext) -> None:
        """Manages the server's autorole"""
        await ctx.send_help('config autorole')

    @autorole.command(name="set", aliases=['add'], level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def setautoroles(self, ctx, *, role: Role) -> None:
        """Sets an auto role for the server"""
        await self.add_config_key(ctx.guild.id, "autorole", role.id)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Successfully set {role.name} as an auto role.")

    @autorole.command(name='remove', level=CommandLevel.Admin)
    @has_guild_permissions(manage_roles=True)
    async def removeautoroles(self, ctx: LightningContext) -> None:
        """Removes the auto role that's configured"""
        res = await self.remove_config_key(ctx.guild.id, "autorole")

        if res == "DELETE 0":
            await ctx.send("This server never had an autorole setup!")
            return

        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send("Successfully removed the server's autorole")

    async def apply_users_roles(self, member: discord.Member, *, reapply=False, punishments_only=True, all=False):
        query = "SELECT roles, punishment_roles FROM roles WHERE guild_id=$1 AND user_id=$2;"
        record = await self.bot.pool.fetchrow(query, member.guild.id, member.id)
        roles = []

        def get_and_append(r):
            role = member.guild.get_role(r)
            if role:
                roles.append(role)
            else:
                record['punishment_roles'].remove(role)

        if record['punishment_roles']:
            for role in record['punishment_roles']:
                get_and_append(role)

            if len(record['punishment_roles']) != 0:
                query = "UPDATE roles SET punishment_roles=$1 WHERE guild_id=$2 AND user_id=$3;"
                await self.bot.pool.execute(query, member.guild.id, member.id)

            await member.add_roles(*roles, reason="Applying previous punishment roles")

            if punishments_only:
                return

        if record['roles'] and reapply:
            for role in record['roles']:
                get_and_append(role)
            await member.add_roles(*roles, reason="Applying old roles back.")

    @LightningCog.listener()
    async def on_member_remove(self, member):
        record = await self.bot.get_guild_bot_config(member.guild.id)

        if not record.flags.role_reapply or len(member.roles) == 0:
            return

        query = """INSERT INTO roles (guild_id, user_id, roles)
                   VALUES ($1, $2, $3::bigint[])
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET roles = EXCLUDED.roles;"""
        await self.bot.pool.execute(query, member.guild.id, member.id,
                                    [r.id for r in member.roles if r is not r.is_default()])

    @LightningCog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        record = await self.bot.get_guild_bot_config(member.guild.id)

        if not record.autorole:
            await self.apply_users_roles(member, reapply=bool(record.flags.role_reapply))
            return

        role = member.guild.get_role(record.autorole)
        if not role:
            await self.apply_users_roles(member, reapply=record.flags.role_reapply)
            # Role is deleted
            await self.remove_config_key(member.guild.id, "autorole")
            await self.bot.get_guild_bot_config.invalidate(member.guild.id)
            return

        await self.apply_users_roles(member, reapply=bool(record.flags.role_reapply))

        if role not in member.roles:
            with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                await member.add_roles(role, reason="Applying configured autorole")

    # Mute role

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 60.0, commands.BucketType.guild)
    async def muterole(self, ctx: LightningContext, *, role: Role = None) -> None:
        """Handles mute role configuration.

        This command allows you to set the mute role for the server or view the configured mute role."""
        if not role:
            ret = await self.get_mod_config(ctx)
            if not ret or ret.mute_role(ctx) is None:
                return await ctx.send("There is no mute role setup!")

            mute = ret.mute_role(ctx)
            await ctx.send(f"The current mute role is set to {mute.name} ({mute.id})")
            return

        if role.is_default():
            await ctx.send('You cannot use the @\u200beveryone role.')
            return

        await self.add_config_key(ctx.guild.id, "mute_role_id", role.id, column="guild_mod_config")
        await self.invalidate_config(ctx)
        await ctx.send(f"Successfully set the mute role to {role.name}")

    @muterole.command(name="reset", aliases=['delete', 'remove'], level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def delete_mute_role(self, ctx: LightningContext) -> None:
        """Deletes the configured mute role."""
        query = """UPDATE guild_mod_config SET mute_role_id=NULL
                   WHERE guild_id=$1;
                """
        await self.bot.pool.execute(query, ctx.guild.id)
        await self.invalidate_config(ctx)
        await ctx.send("Successfully removed the configured mute role.")

    async def update_mute_role_permissions(self, role: discord.Role, guild: discord.Guild, author) -> tuple:
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

    @muterole.command(name="update", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def mute_role_perm_update(self, ctx: LightningContext) -> None:
        """Updates the permission overwrites of the mute role.

        This sets the permissions to Send Messages and Add Reactions as False
        on every text channel that the bot can set permissions for."""
        config = await self.get_mod_config(ctx)
        if config is None or config.mute_role(ctx) is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        success, failed, skipped = await self.update_mute_role_permissions(config.mute_role(ctx),
                                                                           ctx.guild, ctx.author)

        await ctx.send(f"Updated {success} channel overrides successfully, {failed} channels failed, and "
                       f"{skipped} channels were skipped.")

    @muterole.command(name="unbind", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def muterole_unbind(self, ctx: LightningContext) -> None:
        """Unbinds the mute role from all users"""
        config = await self.get_mod_config(ctx)
        if config is None or config.mute_role_id(ctx) is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        query = "SELECT user_id FROM roles WHERE guild_id=$1 AND $2=ANY(punishment_roles);"
        users = await self.bot.pool.fetchval(query, ctx.guild.id, config.mute_role_id)

        confirm = await ctx.prompt(f"Are you sure you want to unbind the mute role from {plural(len(users)):user}?")
        if not confirm:
            return

        query = "UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1) WHERE guild_id=$2;"
        await self.bot.pool.execute(query, config.mute_role_id, ctx.guild.id)
        await ctx.send(f"Unbound {plural(len(users)):user} from the mute role.")

    # AutoMod

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    async def automod(self, ctx: LightningContext) -> None:
        await ctx.send_help("config automod")

    @automod.command(level=CommandLevel.Admin, enabled=False)
    async def jointhreshold(self, ctx: LightningContext, joins: Optional[int] = 3, seconds: Optional[int] = 6) -> None:
        if not joins and not seconds:
            await self.remove_config_key(ctx.guild.id, "automod_jointhreshold", column="guild_mod_config")
            await ctx.send("Reset join threshold.")
        ...

    # COMMAND OVERRIDES

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions(self, ctx: LightningContext) -> None:
        """Manages user permissions for the bot"""
        await ctx.send_help("config permissions")

    async def adjust_level(self, guild_id, level, _id, *, adjuster) -> bool:
        if level.lower() not in ('user', 'trusted', 'mod', 'admin', 'owner', 'blocked'):
            raise

        record = await self.bot.get_guild_bot_config(guild_id)
        if record.permissions is None or record.permissions.levels is None:
            perms = {"LEVELS": {}}
        else:
            perms = record.permissions.raw()

        level = level.upper()

        v: list = perms["LEVELS"].get(level, [])

        def append():
            if _id in v:
                return False
            else:
                v.append(_id)
                return True

        def remove():
            if _id not in v:
                return False
            else:
                v.remove(_id)
                return True

        adj = {"append": append,
               "remove": remove}

        res = adj[adjuster]()

        if res is False:  # Nothing changed
            return res

        perms["LEVELS"][level] = v
        await self.add_config_key(guild_id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(guild_id)
        return res

    @permissions.command(name='add', level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions_add(self, ctx: LightningContext, level: convert_to_level, _id: discord.Member) -> None:
        """Adds a user to a level"""
        await self.adjust_level(ctx.guild.id, level, _id.id, adjuster="append")
        await ctx.tick(True)

    @permissions.command(name='remove', level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions_remove(self, ctx: LightningContext, level: convert_to_level,
                                 _id: Union[discord.Member, int]) -> None:
        """Removes a user from a level"""
        added = await self.adjust_level(ctx.guild.id, _id.id, level, adjuster="remove")
        if not added:
            await ctx.send(f"{_id} was never added to that level.")
            return

        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def blockcommand(self, ctx: LightningContext, command: ValidCommandName) -> None:
        """Blocks a command to everyone."""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = {"COMMAND_OVERRIDES": {}}
        else:
            perms = record.permissions.raw()

        if command in perms["COMMAND_OVERRIDES"]:
            perms['COMMAND_OVERRIDES'][command]["LEVEL"] = CommandLevel.Disabled.value
        else:
            perms['COMMAND_OVERRIDES'].update({command: {"LEVEL": CommandLevel.Disabled.value}})

        await self.add_config_key(ctx.guild.id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def unblockcommand(self, ctx, command: ValidCommandName) -> None:
        """Unblocks a command"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = {"COMMAND_OVERRIDES": {}}
        else:
            perms = record.permissions.raw()

        if command in perms['COMMAND_OVERRIDES']:
            perms['COMMAND_OVERRIDES'][command].pop("LEVEL", None)
        else:
            await ctx.send(f"{command} was never blocked")
            return

        await self.add_config_key(ctx.guild.id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)  # TODO: Replace with an owner check
    async def fallback(self, ctx, boolean: bool) -> None:
        """Toggles the fallback permissions feature"""
        await self.add_config_key(ctx.guild.id, "fallback", boolean, column="guild_permissions")
        await self.bot.get_permissions_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin, name="show")
    @has_guild_permissions(manage_guild=True)
    async def show_perms(self, ctx: LightningContext) -> None:
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        await ctx.send(f"```json\n{record.permissions.raw()}```")

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def reset(self, ctx: LightningContext) -> None:
        """Resets all permission configuration."""
        query = "UPDATE guild_config SET permissions = permissions - 'LEVELS' WHERE guild_id=$1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @has_guild_permissions(manage_guild=True)
    @permissions.group(invoke_without_command=True, level=CommandLevel.Admin)
    async def commandoverrides(self, ctx: LightningContext) -> None:
        """Manages configuration for command overrides.

        This allows you to allow certain people or roles to use a command without needing a role recognized as a level.
        """
        await ctx.send_help("config permissions commandoverrides")

    @has_guild_permissions(manage_guild=True)
    @commandoverrides.command(require_var_positional=True, level=CommandLevel.Admin)
    async def add(self, ctx: LightningContext, command: ValidCommandName,
                  *ids: Union[discord.Role, discord.Member]) -> None:
        """Allows users/roles to run a command"""
        # MAYBE TODO: Inform user if some ids are already registered...
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = {"COMMAND_OVERRIDES": {}}
        else:
            perms = record.permissions.raw()

        uids = set(r.id for r in ids)

        if command in perms["COMMAND_OVERRIDES"]:
            overrides = perms['COMMAND_OVERRIDES'][command].get("ID_OVERRIDES", [])
            overrides.extend([r for r in uids if r not in overrides])
        else:
            perms['COMMAND_OVERRIDES'].update({command: {"ID_OVERRIDES": list(uids)}})

        await self.add_config_key(ctx.guild.id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @has_guild_permissions(manage_guild=True)
    @commandoverrides.command(name='changelevel', level=CommandLevel.Admin)
    async def change_command_level(self, ctx: LightningContext, command: ValidCommandName,
                                   level: convert_to_level_value):
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = {"COMMAND_OVERRIDES": {}}
        else:
            perms = record.permissions.raw()

        if command in perms['COMMAND_OVERRIDES']:
            perms['COMMAND_OVERRIDES'][command]["LEVEL"] = level.value
        else:
            perms['COMMAND_OVERRIDES'].update({command: {"LEVEL": level.value}})

        await self.add_config_key(ctx.guild.id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @has_guild_permissions(manage_guild=True)
    @commandoverrides.command(level=CommandLevel.Admin)
    async def removeall(self, ctx: LightningContext, command: ValidCommandName) -> None:
        """Removes all overrides from a command"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = {"COMMAND_OVERRIDES": {}}
        else:
            perms = record.permissions.raw()

        resp = perms['COMMAND_OVERRIDES'].pop(command, None)

        await self.add_config_key(ctx.guild.id, "permissions", perms)

        if resp is not None:
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)

        await ctx.tick(True)

    @has_guild_permissions(manage_guild=True)
    @commandoverrides.command(name="reset", level=CommandLevel.Admin)
    async def reset_overrides(self, ctx: LightningContext) -> None:
        """Removes all command overrides for this server"""
        query = "UPDATE guild_config SET permissions = permissions - 'COMMAND_OVERRIDES' WHERE guild_id=$1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Configuration(bot))

    if "beta_prefix" in bot.config['bot']:
        bot.remove_command("config prefix")
