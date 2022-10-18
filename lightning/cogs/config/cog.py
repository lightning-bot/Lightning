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
from __future__ import annotations

import collections
import logging
from typing import Any, Dict, List, Literal, Optional, Union

import discord
from discord.ext import commands
from sanctum import DataConflict, NotFound

from lightning import CommandLevel, GuildContext, LightningCog, cache, group
from lightning.cogs.config import ui
from lightning.cogs.config.converters import (AutoModDuration,
                                              AutoModDurationResponse,
                                              IgnorableEntities)
from lightning.constants import (AUTOMOD_EVENT_NAMES_LITERAL,
                                 AUTOMOD_EVENT_NAMES_MAPPING)
from lightning.converters import Role, ValidCommandName, convert_to_level_value
from lightning.formatters import plural
from lightning.models import GuildModConfig
from lightning.utils.checks import has_guild_permissions
from lightning.utils.helpers import ticker
from lightning.utils.paginator import Paginator
from lightning.utils.time import ShortTime

log = logging.getLogger(__name__)


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

    async def invalidate_config(self, ctx: GuildContext, *, config_name="mod_config") -> bool:
        """Function to reduce duplication for invalidating a cached guild mod config"""
        c = cache.registry.get(config_name)
        return await c.invalidate(str(ctx.guild.id))

    async def remove_config_key(self, guild_id: int, key: str, *, table='guild_config') -> str:
        query = f"UPDATE {table} SET {key} = NULL WHERE guild_id=$1;"
        return await self.bot.pool.execute(query, guild_id)

    @group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def config(self, ctx: GuildContext) -> None:
        """Manages most of the configuration for the bot"""
        await ctx.send_help('config')

    async def add_prefix(self, guild: discord.Guild, prefix: list, *, connection=None) -> None:
        """Adds a prefix to the guild's config"""
        query = """INSERT INTO guild_config (guild_id, prefixes)
                   VALUES ($1, $2::text[]) ON CONFLICT (guild_id)
                   DO UPDATE SET
                        prefix = EXCLUDED.prefix;
                """
        connection = connection or self.bot.pool
        await connection.execute(query, guild.id, list(prefix))

    async def get_guild_prefixes(self, guild_id: int, connection=None) -> list:
        connection = connection or self.bot.pool
        query = """SELECT prefixes
                   FROM guild_config
                   WHERE guild_id=$1;"""
        val = await connection.fetchval(query, guild_id)
        return val or []

    async def delete_prefix(self, guild_id: int, prefixes: list) -> str:
        """Deletes a prefix"""
        if not prefixes:
            query = "UPDATE guild_config SET prefixes = NULL WHERE guild_id = $1;"
            args = [guild_id]
        else:
            query = "UPDATE guild_config SET prefixes = $1 WHERE guild_id = $2;"
            args = [prefixes, guild_id]

        return await self.bot.pool.execute(query, *args)

    @config.command(aliases=['prefixes'], level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def prefix(self, ctx: GuildContext) -> None:
        """Manages the server's custom prefixes"""
        prompt = ui.Prefix(context=ctx)
        await prompt.start(wait=False)

    async def add_config_key(self, guild_id, key, value, *, table="guild_config") -> str:
        query = f"""INSERT INTO {table} (guild_id, {key})
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET {key} = EXCLUDED.{key};"""
        return await self.bot.pool.execute(query, guild_id, value)

    @config.command(level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_messages=True, view_audit_log=True, send_messages=True)
    @has_guild_permissions(manage_guild=True)
    async def logging(self, ctx, *, channel: discord.TextChannel = commands.CurrentChannel):
        """Sets up logging for the server via a menu"""
        await ui.Logging(channel, context=ctx, timeout=180.0).start(wait=False)

    @config.command(level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def autorole(self, ctx: GuildContext) -> None:
        """Manages the server's autorole

        If this command is called alone, an interactive menu will start."""
        await ui.AutoRole(context=ctx, timeout=180).start()

    # Mute role

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 60.0, commands.BucketType.guild)
    async def muterole(self, ctx: GuildContext, *,
                       role: Optional[discord.Role] = commands.param(converter=Role, default=None)) -> None:
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

    @muterole.command(name="reset", aliases=['delete', 'remove'], level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def delete_mute_role(self, ctx: GuildContext) -> None:
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
                overwrite.send_messages_in_threads = False
                overwrite.use_application_commands = False
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
    async def mute_role_perm_update(self, ctx: GuildContext) -> None:
        """Updates the permission overwrites of the mute role.

        This sets the permissions to Send Messages and Add Reactions as False
        on every text channel that the bot can set permissions for."""
        config = await self.get_mod_config(ctx)
        if config is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        role = config.get_mute_role()

        success, failed, skipped = await self.update_mute_role_permissions(role,
                                                                           ctx.guild, ctx.author)

        await ctx.send(f"Updated {success} channel overrides successfully, {failed} channels failed, and "
                       f"{skipped} channels were skipped.")

    @muterole.command(name="unbind", level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True, manage_roles=True)
    async def muterole_unbind(self, ctx: GuildContext) -> None:
        """Unbinds the mute role from all users"""
        config = await self.get_mod_config(ctx)
        if config is None:
            await ctx.send("No mute role is currently set. You can set one with"
                           f"`{ctx.prefix}config muterole <role>`.")
            return

        query = "SELECT COUNT(*) FROM roles WHERE guild_id=$1 AND $2 = ANY(punishment_roles);"
        users = await self.bot.pool.fetchval(query, ctx.guild.id, config.mute_role_id)

        confirm = await ctx.confirm(f"Are you sure you want to unbind the mute role from {plural(users):user}?")
        if not confirm:
            return

        query = "UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1) WHERE guild_id=$2;"
        await self.bot.pool.execute(query, config.mute_role_id, ctx.guild.id)
        await ctx.send(f"Unbound {plural(users):user} from the mute role.")

    # AutoMod

    @config.group(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def automod(self, ctx: GuildContext) -> None:
        """Commands to configure Lightning's Auto-Moderation"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @automod.command(level=CommandLevel.Admin, name='ignore', require_var_positional=True)
    @has_guild_permissions(manage_guild=True)
    async def automod_default_ignores(self, ctx: GuildContext, *entities: IgnorableEntities):
        """Specifies what roles, members, or channels will be ignored by AutoMod by default."""
        try:
            config = await self.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            config = {'default_ignores': []}

        config['default_ignores'].extend(e.id for e in entities if e.id not in config['default_ignores'])

        await self.bot.api.bulk_upsert_guild_automod_default_ignores(ctx.guild.id, config['default_ignores'])
        await ctx.send(f"Now ignoring {', '.join([e.mention for e in entities])}")
        await self.invalidate_config(ctx, config_name="guild_automod")

    @automod.command(level=CommandLevel.Admin, name='unignore', require_var_positional=True)
    @has_guild_permissions(manage_guild=True)
    async def automod_default_unignore(self, ctx: GuildContext, *entities: IgnorableEntities) -> None:
        """Specify roles, members, or channels to remove from AutoMod default ignores."""
        try:
            config = await self.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            await ctx.send("You have not set up any ignores!")
            return

        ignores: List[int] = config['default_ignores']
        if not ignores:
            await ctx.send("You have not set up any ignores!")
            return

        for entity in entities:
            if entity.id in ignores:
                ignores.remove(entity.id)

        await self.bot.api.bulk_upsert_guild_automod_default_ignores(ctx.guild.id, ignores)
        await ctx.send(f"Removed {', '.join(e.mention for e in entities)} from default ignores")
        await self.invalidate_config(ctx, config_name="guild_automod")

    @automod.command(level=CommandLevel.Admin, name='ignored')
    @has_guild_permissions(manage_guild=True)
    async def automod_ignored(self, ctx: GuildContext):
        """Shows what roles, members, or channels are ignored by AutoMod"""
        try:
            config = await self.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            config = {'default_ignores': []}

        # levels: Optional[LevelConfig] = attrgetter('permissions.levels')(await self.bot.get_guild_bot_config())
        levels = None

        if not config['default_ignores'] and not levels:
            await ctx.send("You have no ignores set up!")
            return

        def resolve_snowflake(id: int):
            if g := ctx.guild.get_channel_or_thread(id):
                return g.mention
            return g.mention if (g := ctx.guild.get_role(id)) else f"<@!{id}>"

        pages = Paginator(ui.AutoModIgnoredPages([resolve_snowflake(g) for g in config['default_ignores']],
                          per_page=10), context=ctx)
        await pages.start()

    @automod.group(level=CommandLevel.Admin, name='rules')
    @has_guild_permissions(manage_guild=True)
    async def automod_rules(self, ctx: GuildContext):
        ...

    @automod_rules.command(level=CommandLevel.Admin, name="add")
    @has_guild_permissions(manage_guild=True)
    async def add_automod_rules(self, ctx: GuildContext, type: AUTOMOD_EVENT_NAMES_LITERAL,
                                *, count: str):
        """Adds a new rule to automod.

        You can provide count in the following ways
        To set automod to do something at 5 messages per 10 seconds, you can express it in one of the following ways
        - "5/10s"
        - "5 10"
        """
        if type == "mass-mentions":
            try:
                result = AutoModDurationResponse(int(count), 0)
            except ValueError:
                await ctx.send("Could not convert to an integer")
                return
        else:
            result: AutoModDurationResponse = await AutoModDuration().convert(ctx, count)

        punishment = await ui.prompt_for_automod_punishments(ctx)
        if punishment is None:
            return

        punishment_payload: Dict[str, Any] = {"type": punishment[0]}

        # Discord removed selects so blame them for this
        if punishment[0] in ("BAN", "MUTE"):
            darg = await ctx.confirm("This punishment supports temporary actions!\nWould you like to set a duration for"
                                     " this rule?")
            if darg:
                m = await ctx.ask("What would you like the duration to be?")
                if not m:
                    return

                duration = ShortTime(m.content)
                punishment_payload['duration'] = duration.delta.seconds

        payload = {"guild_id": ctx.guild.id,
                   "type": type,
                   "count": result.count,
                   "seconds": result.seconds,
                   "punishment": punishment_payload}
        try:
            await self.bot.api.create_guild_automod_rule(ctx.guild.id, payload)
        except DataConflict:
            await ctx.send("This rule has already been set up!\nIf you want to edit this rule, please remove it and"
                           " then re-run this command again!")
            return

        await ctx.send(f"Successfully set up {AUTOMOD_EVENT_NAMES_MAPPING[type]}!")
        await self.invalidate_config(ctx, config_name="guild_automod")

    @automod_rules.command(level=CommandLevel.Admin, name="remove")
    @has_guild_permissions(manage_guild=True)
    async def remove_automod_rule(self, ctx: GuildContext, rule: AUTOMOD_EVENT_NAMES_LITERAL):
        """Removes an existing automod rule"""
        try:
            await self.bot.api.delete_guild_automod_rule(ctx.guild.id, rule)
        except NotFound:
            await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was never set up!")
            return

        await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was removed.")
        await self.invalidate_config(ctx, config_name="guild_automod")

    # COMMAND OVERRIDES

    @config.group(invoke_without_command=True, level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions(self, ctx: GuildContext) -> None:
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
    async def permissions_add(self, ctx: GuildContext, level: Literal['trusted', 'mod', 'admin'],
                              _id: Union[discord.Role, discord.Member]) -> None:
        """Adds a user or a role to a level"""
        await self.adjust_level(ctx.guild.id, level, _id, adjuster="append")
        await ctx.tick(True)

    @permissions.command(name='remove', level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def permissions_remove(self, ctx: GuildContext, level: Literal['trusted', 'mod', 'admin'],
                                 _id: Union[discord.Member, discord.Role, int]) -> None:
        """Removes a user or a role from a level"""
        added = await self.adjust_level(ctx.guild.id, _id, level, adjuster="remove")
        if not added:
            await ctx.send(f"{_id} was never added to that level.")
            return

        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def blockcommand(self, ctx: GuildContext, command: ValidCommandName) -> None:
        """Blocks a command to everyone."""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if record.permissions is None:
            perms = collections.defaultdict(dict)
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
    async def unblockcommand(self, ctx: GuildContext, command: ValidCommandName) -> None:
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
    async def fallback(self, ctx: GuildContext, boolean: bool) -> None:
        """Toggles the fallback permissions feature"""
        await self.add_config_key(ctx.guild.id, "fallback", boolean, table="guild_permissions")
        await self.bot.get_permissions_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @permissions.command(level=CommandLevel.Admin, name="show")
    @has_guild_permissions(manage_guild=True)
    async def show_perms(self, ctx: GuildContext) -> None:
        """Shows raw permissions"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or record.permissions is None:
            await ctx.send("You have not setup this feature!")
            return

        await ctx.send(f"```json\n{record.permissions.raw()}```")

    async def debug_command_perms(self, ctx: GuildContext, command, member=None):
        ctx.author = member or ctx.author

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
    async def debug_permissions(self, ctx: GuildContext, command: ValidCommandName,
                                member: discord.Member = commands.Author):
        """Debugs a member's permissions to use a command."""
        command = self.bot.get_command(command)
        await self.debug_command_perms(ctx, command, member)

    @permissions.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def reset(self, ctx: GuildContext) -> None:
        """Resets all permission configuration."""
        query = "UPDATE guild_config SET permissions = permissions - 'LEVELS' WHERE guild_id=$1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)

    @has_guild_permissions(manage_guild=True)
    @permissions.group(invoke_without_command=True, level=CommandLevel.Admin)
    async def commandoverrides(self, ctx: GuildContext) -> None:
        """Manages configuration for command overrides.

        This allows you to allow certain people or roles to use a command without needing a role recognized as a level.
        """
        await ctx.send_help("config permissions commandoverrides")

    @has_guild_permissions(manage_guild=True)
    @commandoverrides.command(require_var_positional=True, level=CommandLevel.Admin)
    async def add(self, ctx: GuildContext, command: ValidCommandName,
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
    async def change_command_level(self, ctx: GuildContext, command: ValidCommandName,
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
    async def removeall(self, ctx: GuildContext, command: ValidCommandName) -> None:
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
    async def reset_overrides(self, ctx: GuildContext) -> None:
        """Removes all command overrides for this server"""
        query = "UPDATE guild_config SET permissions = permissions - 'COMMAND_OVERRIDES' WHERE guild_id=$1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.tick(True)
