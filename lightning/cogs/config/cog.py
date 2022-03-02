"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
import logging
from io import StringIO
from typing import Optional, Union

import discord
from discord.ext import commands, menus
from discord.ext.menus.views import ViewMenu

from lightning import (CommandLevel, ConfigFlags, LightningCog,
                       LightningContext, ModFlags, cache, command)
from lightning import flags as lflags
from lightning import group
from lightning.cogs.config import ui
from lightning.converters import (Prefix, Role, ValidCommandName,
                                  convert_to_level, convert_to_level_value)
from lightning.formatters import plural
from lightning.models import GuildModConfig
from lightning.utils.automod_parser import from_attachment
from lightning.utils.checks import has_guild_permissions
from lightning.utils.helpers import ticker

log = logging.getLogger(__name__)


class ConfigViewerMenu(ViewMenu):
    def give_help(self) -> discord.Embed:
        messages = [
            'Welcome to the interactive config viewer!\n',
            'This interactively allows you to see configuration settings of the bot by navigating with reactions. ',
            'They are as follows:\n',
        ]

        for emoji, button in self.buttons.items():
            messages.append(f'{emoji} {button.action.__doc__}')

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
            embed.add_field(name="RoleSaver", value="Enabled" if record.flags.role_reapply else "Disabled",
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
            if (role := discord.utils.get(self.ctx.guild.roles, id=obj.mute_role_id)) is not None:
                embed.add_field(name="Permanent Mute Role", value=f"{role.name} (ID: {role.id})")

        if obj.temp_mute_role_id:
            role = discord.utils.get(self.ctx.guild.roles, id=obj.temp_mute_role_id)
            if role is not None:
                embed.add_field(name="Temporary Mute Role", value=f"{role.name} (ID: {role.id})")

        # Warn Thresholds
        if obj.warn_kick or obj.warn_ban:
            msg = []
            if obj.warn_kick:
                msg.append(f"Kick: at {obj.warn_kick} warns\n")
            if obj.warn_ban:
                msg.append(f"Ban: at {obj.warn_ban}+ warns\n")
            embed.add_field(name="Warn Thresholds", value="".join(msg))

        await self.message.edit(embed=embed)

    @menus.button('\N{INFORMATION SOURCE}\ufe0f')
    async def show_help(self, payload) -> None:
        """Shows help"""
        await self.message.edit(embed=self.give_help())


Features = {"role saver": (ConfigFlags.role_reapply, "Now saving member roles.", "No longer saving member roles."),
            "invoke delete": (ConfigFlags.invoke_delete, "Now deleting successful command invocation messages",
                              "No longer deleting successful command invocation messages")}
AutoModFeatures = {"delete longer messages": (ModFlags.delete_longer_messages,
                                              "deleting messages over 2000 characters"),
                   "delete stickers": (ModFlags.delete_stickers, "deleting messages containing a sticker.")}


def convert_to_feature(argument):
    if argument.lower() in Features.keys():
        return Features[argument.lower()]
    else:
        raise commands.BadArgument(f"\"{argument}\" is not a valid feature flag.")


def convert_to_automod_feature(argument):
    if argument.lower() in AutoModFeatures.keys():
        return AutoModFeatures[argument.lower()]
    else:
        raise commands.BadArgument(f"\"{argument}\" is not a valid feature flag.")


class Configuration(LightningCog):
    """Server configuration commands"""

    async def cog_check(self, ctx) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def get_mod_config(self, ctx, *, connection=None) -> Optional[GuildModConfig]:
        connection = connection or self.bot.pool
        query = """SELECT * FROM guild_mod_config WHERE guild_id=$1"""
        ret = await connection.fetchrow(query, ctx.guild.id)
        if not ret:
            return None
        return GuildModConfig(ret, self.bot)

    async def invalidate_config(self, ctx: LightningContext, *, config_name="mod_config") -> bool:
        """Function to reduce duplication for invalidating a cached guild mod config"""
        c = cache.registry.get(config_name)
        return await c.invalidate(str(ctx.guild.id))

    @command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def settings(self, ctx):
        menu = ConfigViewerMenu(timeout=60.0, clear_reactions_after=True)
        await menu.start(ctx)

    async def remove_config_key(self, guild_id: int, key: str, *, table='guild_config') -> str:
        query = f"UPDATE {table} SET {key} = NULL WHERE guild_id=$1;"
        return await self.bot.pool.execute(query, guild_id)

    @group(invoke_without_command=True, level=CommandLevel.Admin)
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
        if not prefixes:
            query = "UPDATE guild_config SET prefix = NULL WHERE guild_id = $1;"
            args = [guild_id]
        else:
            query = "UPDATE guild_config SET prefix = $1 WHERE guild_id = $2;"
            args = [prefixes, guild_id]

        return await self.bot.pool.execute(query, *args)

    @config.group(aliases=['prefixes'], invoke_without_command=True, level=CommandLevel.Admin)
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

        Example: `{prefix}prefix remove "lightning "` removes the "lightning " prefix.
        """
        prefixes = await self.get_guild_prefixes(ctx.guild.id)
        if prefix not in prefixes:
            await ctx.send(f"{prefix} was never added as a custom prefix.")
            return

        prefixes.remove(prefix)
        await self.delete_prefix(ctx.guild.id, prefixes)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Removed `{prefix}`")

    async def add_config_key(self, guild_id, key, value, *, table="guild_config") -> str:
        query = f"""INSERT INTO {table} (guild_id, {key})
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET {key} = EXCLUDED.{key};"""
        return await self.bot.pool.execute(query, guild_id, value)

    @config.command(level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_messages=True, view_audit_log=True, send_messages=True)
    @has_guild_permissions(manage_guild=True)
    async def logging(self, ctx, *, channel: discord.TextChannel = commands.default.CurrentChannel):
        """Sets up logging for the server via a menu"""
        await ui.Logging(channel, timeout=180.0).start(ctx)

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
        toggle = record.flags - flag if flag in record.flags else \
            record.flags | flag
        await self.add_config_key(guild_id, "flags", int(toggle))
        await self.bot.get_guild_bot_config.invalidate(guild_id)
        return toggle

    @config.command(level=CommandLevel.Admin)
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

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def autorole(self, ctx: LightningContext) -> None:
        """Manages the server's autorole

        If this command is called alone, an interactive menu will start."""
        await ui.AutoRole(timeout=180.0).start(ctx)

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
            if not ret:
                await ctx.send("There is no mute role setup!")
                return

            mute = ret.get_mute_role(ctx)
            await ctx.send(f"The current mute role is set to {mute.name} ({mute.id})")
            return

        await self.add_config_key(ctx.guild.id, "mute_role_id", role.id, table="guild_mod_config")
        await self.invalidate_config(ctx)
        await ctx.send(f"Successfully set the mute role to {role.name}")

    @muterole.command(name="temp", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def set_temp_mute_role(self, ctx: LightningContext, *, role: Role = None) -> None:
        if not role:
            ret = await self.get_mod_config(ctx)
            if not ret:
                await ctx.send("There is no mute role setup!")
                return

            mute = ret.get_temp_mute_role(ctx, fallback=False)
            await ctx.send(f"The current temporary mute role is set to {mute.name} ({mute.id})")
            return

        await self.add_config_key(ctx.guild.id, "temp_mute_role_id", role.id, table="guild_mod_config")
        await self.invalidate_config(ctx)
        await ctx.send(f"Successfully set the temporary mute role to {role.name}")

    @lflags.add_flag("--temp", "-T", is_bool_flag=True, help="Whether to remove the temp mute role")
    @muterole.command(name="reset", aliases=['delete', 'remove'], level=CommandLevel.Admin, cls=lflags.FlagCommand)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def delete_mute_role(self, ctx: LightningContext, **flags) -> None:
        """Deletes the configured mute role."""
        if flags['temp'] is False:
            query = """UPDATE guild_mod_config SET mute_role_id=NULL
                       WHERE guild_id=$1;
                    """
        else:
            query = """UPDATE guild_mod_config SET temp_mute_role_id=NULL
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

    @lflags.add_flag("--temp", "-T", is_bool_flag=True, help="Whether to use the temp mute role")
    @muterole.command(name="update", level=CommandLevel.Admin, cls=lflags.FlagCommand)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def mute_role_perm_update(self, ctx: LightningContext, **flags) -> None:
        """Updates the permission overwrites of the mute role.

        This sets the permissions to Send Messages and Add Reactions as False
        on every text channel that the bot can set permissions for."""
        config = await self.get_mod_config(ctx)
        if config is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        role = config.get_mute_role() if flags['temp'] is False else config.get_temp_mute_role(fallback=False)

        success, failed, skipped = await self.update_mute_role_permissions(role,
                                                                           ctx.guild, ctx.author)

        await ctx.send(f"Updated {success} channel overrides successfully, {failed} channels failed, and "
                       f"{skipped} channels were skipped.")

    @muterole.command(name="unbind", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def muterole_unbind(self, ctx: LightningContext) -> None:
        """Unbinds the mute role from all users"""
        config = await self.get_mod_config(ctx)
        if config is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        query = "SELECT COUNT(*) FROM roles WHERE guild_id=$1 AND $2 = ANY(punishment_roles);"
        users = await self.bot.pool.fetchval(query, ctx.guild.id, config.mute_role_id)

        confirm = await ctx.prompt(f"Are you sure you want to unbind the mute role from {plural(users):user}?")
        if not confirm:
            return

        query = "UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1) WHERE guild_id=$2;"
        await self.bot.pool.execute(query, config.mute_role_id, ctx.guild.id)
        await ctx.send(f"Unbound {plural(users):user} from the mute role.")

    # AutoMod

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    async def automod(self, ctx: LightningContext) -> None:
        await ctx.send_help("config automod")

    async def toggle_automod_feature_flag(self, guild_id: int, flag: ModFlags) -> ModFlags:
        """Toggles an automod feature flag for a guild

        Parameters
        ----------
        guild_id : int
            The ID of the server
        flag : ModFlags
            The flag that is being toggled.

        Returns
        -------
        ModFlags
            Returns the newly created flags.
        """
        record = await self.bot.get_mod_config(guild_id)
        toggle = record.flags - flag if flag in record.flags else record.flags | flag
        await self.add_config_key(guild_id, "flags", int(toggle), table="guild_mod_config")
        await self.invalidate_config(guild_id)
        return toggle

    @automod.command(name="toggle", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def toggle_auto(self, ctx: LightningContext, feature: convert_to_automod_feature) -> None:
        flag, msg = feature
        toggle = await self.toggle_automod_feature_flag(ctx.guild.id, flag)

        if flag in toggle:
            await ctx.send(f"Now {msg}")
        else:
            await ctx.send(f"No longer {msg}")

    @automod.command(level=CommandLevel.Admin, aliases=['upload'])
    @has_guild_permissions(manage_guild=True)
    async def uploadconfig(self, ctx: LightningContext):
        """Adds an attached .toml file to the automod settings"""
        if not ctx.message.attachments:
            await ctx.send("Attach a TOML file.")
            return

        raw_cfg = None
        for attachment in ctx.message.attachments:
            if attachment.filename.endswith(".toml"):
                raw_cfg = attachment

        if not raw_cfg:
            await ctx.send("Could not find an .TOML file attached to this message...")
            return

        try:
            await from_attachment(attachment)
        except Exception as e:
            await ctx.send(str(e))
            return

        query = """INSERT INTO automod (guild_id, config)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET config=EXCLUDED.config;"""
        await self.bot.pool.execute(query, ctx.guild.id, str(await attachment.read(), "UTF-8"))

        await ctx.send("Configured automod according to your settings.")
        c = self.bot.get_cog("AutoMod")
        await c.get_automod_config.invalidate(ctx.guild.id)

    @automod.command(level=CommandLevel.Admin, aliases=['download'])
    @has_guild_permissions(manage_guild=True)
    async def downloadconfig(self, ctx: LightningContext):
        """Sends you the current configuration for automoderation"""
        query = """SELECT config FROM automod WHERE guild_id=$1;"""
        record = await self.bot.pool.fetchval(query, ctx.guild.id)
        if not record:
            await ctx.send("This server doesn't have automod setup.")
            return

        fp = StringIO(record)
        fp.seek(0)
        await ctx.send(file=discord.File(fp, "config.toml"))

    # COMMAND OVERRIDES

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions(self, ctx: LightningContext) -> None:
        """Manages user permissions for the bot"""
        await ctx.send_help("config permissions")

    async def adjust_level(self, guild_id, level, _id, *, adjuster) -> bool:
        if level.lower() not in ('user', 'trusted', 'mod', 'admin', 'owner', 'blocked'):
            raise

        if not hasattr(_id, "id"):
            _id = discord.Object(id=_id)

        if isinstance(_id, discord.Role):
            role_id = True
        else:
            role_id = False

        record = await self.bot.get_guild_bot_config(guild_id)
        if record is None or record.permissions is None or record.permissions.levels is None:
            perms = {"LEVELS": {}}
        else:
            perms = record.permissions.raw()

        level_name = level.upper()
        p = perms['LEVELS'].get(level_name, {level_name: {}})
        perms['LEVELS'][level_name] = {"ROLE_IDS": p.get("ROLE_IDS", []),
                                       "USER_IDS": p.get("USER_IDS", [])}

        def append(d):
            if _id in d:
                return False
            else:
                d.append(_id.id)
                return True

        def remove(d):
            if _id not in d:
                return False
            else:
                d.remove(_id.id)
                return True

        adj = {"append": append,
               "remove": remove}

        if not role_id:
            res = adj[adjuster](perms['LEVELS'][level_name]['USER_IDS'])
        else:  # This should be a role id
            res = adj[adjuster](perms['LEVELS'][level_name]['ROLE_IDS'])

        if res is False:  # Nothing changed
            return res

        await self.add_config_key(guild_id, "permissions", perms)
        await self.bot.get_guild_bot_config.invalidate(guild_id)
        return res

    @permissions.command(name='add', level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions_add(self, ctx: LightningContext, level: convert_to_level,
                              _id: Union[discord.Role, discord.Member]) -> None:
        """Adds a user or a role to a level"""
        await self.adjust_level(ctx.guild.id, level, _id, adjuster="append")
        await ctx.tick(True)

    @permissions.command(name='remove', level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions_remove(self, ctx: LightningContext, level: convert_to_level,
                                 _id: Union[discord.Member, discord.Role, int]) -> None:
        """Removes a user or a role from a level"""
        added = await self.adjust_level(ctx.guild.id, _id, level, adjuster="remove")
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
    async def unblockcommand(self, ctx: LightningContext, command: ValidCommandName) -> None:
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
    async def fallback(self, ctx: LightningContext, boolean: bool) -> None:
        """Toggles the fallback permissions feature"""
        await self.add_config_key(ctx.guild.id, "fallback", boolean, table="guild_permissions")
        await self.bot.get_permissions_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin, name="show")
    @has_guild_permissions(manage_guild=True)
    async def show_perms(self, ctx: LightningContext) -> None:
        """Shows raw permissions"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or record.permissions is None:
            await ctx.send("You have not setup this feature!")
            return

        await ctx.send(f"```json\n{record.permissions.raw()}```")

    async def debug_command_perms(self, ctx: LightningContext, command, member):
        embed = discord.Embed(title="Debug Result")
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or record.permissions is None:
            res = await command._resolve_permissions(ctx, CommandLevel.User)
            embed.add_field(name="Default Permission Checks", value=ticker(res))
            await ctx.send(embed=embed)
            return

        if record.permissions.levels is None:
            # We're gonna assume they are a user unless otherwise
            user_level = CommandLevel.User
        else:
            user_level = record.permissions.levels.get_user_level(ctx.author.id, ctx.author._roles)

        ovr = record.permissions.command_overrides
        if ovr is not None:
            ids = ctx.author._roles.tolist()
            ids.append(ctx.author.id)

            embed.add_field(name="ID Overriden",
                            value=ticker(ovr.is_command_id_overriden(command.qualified_name, ids)),
                            inline=False)

            embed.add_field(name="Blocked", value=ticker(ovr.is_command_level_blocked(command.qualified_name)),
                            inline=False)
            # Level Overrides
            raw = ovr.get_overrides(command.qualified_name)

            level_overriden = raw.get("LEVEL", None) if raw else None
            value = (user_level.value >= level_overriden) if level_overriden else False
            embed.add_field(name="Level Overriden", value=ticker(value), inline=False)

        user_perms = await command._resolve_permissions(ctx, user_level)
        embed.add_field(name="Default Permission Checks", value=ticker(user_perms), inline=False)
        await ctx.send(embed=embed)

    @permissions.command(level=CommandLevel.Admin, name="debug")
    @has_guild_permissions(manage_guild=True)
    async def debug_permissions(self, ctx: LightningContext, command: ValidCommandName,
                                member: discord.Member = commands.default.Author):
        """Debugs a member's permissions to use a command."""
        # TODO: Debug a member's permissions only...
        command = self.bot.get_command(command)
        await self.debug_command_perms(ctx, command, member)

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

        uids = {r.id for r in ids}

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
        """Overrides a command's level"""
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
