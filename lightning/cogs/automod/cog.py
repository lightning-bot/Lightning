"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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

import contextlib
import datetime
from typing import (TYPE_CHECKING, Annotated, Any, Callable, Dict, List,
                    Literal, Optional, TypedDict, Union)

import discord
from discord import app_commands
from discord.ext import commands
from sanctum.exceptions import DataConflict, NotFound
from unidecode import unidecode

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, cache, hybrid_group)
from lightning.cogs.automod import ui
from lightning.cogs.automod.converters import (AutoModDuration,
                                               AutoModDurationResponse,
                                               IgnorableEntities)
from lightning.cogs.automod.models import (AutomodConfig, GateKeeperConfig,
                                           SpamConfig)
from lightning.constants import (AUTOMOD_ADVANCED_EVENT_NAMES_MAPPING,
                                 AUTOMOD_ALL_EVENT_NAMES_LITERAL,
                                 AUTOMOD_BASIC_EVENT_NAMES_MAPPING,
                                 AUTOMOD_BASIC_EVENTS_LITERAL,
                                 AUTOMOD_EVENT_NAMES_LITERAL,
                                 AUTOMOD_EVENT_NAMES_MAPPING,
                                 COMMON_HOIST_CHARACTERS)
from lightning.enums import ActionType, AutoModPunishmentType
from lightning.events import InfractionEvent
from lightning.models import GuildAutoModRulePunishment, PartialGuild
from lightning.utils.checks import is_server_manager
from lightning.utils.paginator import Paginator
from lightning.utils.time import ShortTime

if TYPE_CHECKING:
    from lightning.cogs.mod import Mod as Moderation
    from lightning.cogs.reminders.cog import Reminders

    class AutoModRulePunishmentPayload(TypedDict):
        type: str
        duration: Optional[str]

    class AutoModMessage(discord.Message):
        guild: discord.Guild
        author: discord.Member


class AutoMod(LightningCog, required=["Moderation"]):
    """Auto-moderation commands"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.gatekeepers: dict[int, GateKeeperConfig] = {}
        # AutoMod stats?

    async def get_gatekeeper_config(self, guild_id: int) -> Optional[GateKeeperConfig]:
        if guild_id in self.gatekeepers:
            return self.gatekeepers[guild_id]

        query = "SELECT * FROM guild_gatekeeper_config WHERE guild_id=$1;"
        record = await self.bot.pool.fetchrow(query, guild_id)
        if not record:
            return

        query = "SELECT * FROM pending_gatekeeper_members WHERE guild_id=$1;"
        mems = await self.bot.pool.fetch(query, guild_id)
        self.gatekeepers[guild_id] = gatekeeper = GateKeeperConfig(self.bot, record, mems)
        return gatekeeper

    def invalidate_gatekeeper(self, guild_id: int):
        gtkp = self.gatekeepers.pop(guild_id, None)
        if gtkp:
            gtkp.gtkp_loop.cancel()

    async def cog_check(self, ctx: LightningContext) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @hybrid_group(level=CommandLevel.Admin)
    @app_commands.guild_only()
    @is_server_manager()
    async def automod(self, ctx: GuildContext) -> None:
        """Commands to configure Lightning's Auto-Moderation"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @automod.command(level=CommandLevel.Admin, name='view')
    @is_server_manager()
    async def automod_view(self, ctx: GuildContext):
        """Allows you to view the current AutoMod configuration"""
        try:
            config = await ctx.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            await ctx.send("This server has not set up Lightning AutoMod yet!")
            return

        fmt = []
        for record in config['rules']:
            if record['type'] in AUTOMOD_BASIC_EVENT_NAMES_MAPPING:
                fmt.append(f"{AUTOMOD_EVENT_NAMES_MAPPING[record['type']]}: Enabled")
            else:
                fmt.append(f"{AUTOMOD_EVENT_NAMES_MAPPING[record['type']]}: {record['count']}/{record['seconds']}s")

        embed = discord.Embed(color=0xf74b06, title="Lightning AutoMod")
        embed.add_field(name="Rules", value="\n".join(fmt) if fmt else "None")

        if default_ignores := config.get("default_ignores"):
            ignores = await self.verify_default_ignores(ctx, default_ignores)
            fmt = "\n".join(x.mention for x in ignores[:10])
            if len(ignores) > 10:
                fmt = f"{fmt}\n and {len(ignores) - 10} more..."
            embed.add_field(name="Ignores", value=fmt)
        else:
            embed.add_field(name="Ignores", value="None")

        if threshold := config.get("warn_threshold"):
            embed.add_field(name="Warn Threshold",
                            value=f"Limit: {threshold}+\nPunishment: {config['warn_punishment']}",
                            inline=False)

        await ctx.send(embed=embed)

    @automod.command(level=CommandLevel.Admin, name='ignore')
    @is_server_manager()
    async def automod_default_ignores(self, ctx: GuildContext, entities: commands.Greedy[IgnorableEntities]):
        """Specifies what roles, members, or channels will be ignored by AutoMod by default."""
        try:
            config = await self.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            config = {'default_ignores': []}

        config['default_ignores'].extend(e.id for e in entities if e.id not in config['default_ignores'])

        await self.bot.api.bulk_upsert_guild_automod_default_ignores(ctx.guild.id, config['default_ignores'])
        await ctx.send(f"Now ignoring {', '.join([e.mention for e in entities])}")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod.command(level=CommandLevel.Admin, name='unignore')
    @is_server_manager()
    async def automod_default_unignore(self, ctx: GuildContext, entities: commands.Greedy[IgnorableEntities]) -> None:
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
        await self.get_automod_config.invalidate(ctx.guild.id)

    async def verify_default_ignores(self, ctx: GuildContext, ignores: List[int]) -> List[IgnorableEntities]:
        unresolved: List[int] = []
        resolved: List[IgnorableEntities] = []
        for snowflake in ignores:
            if g := ctx.guild.get_channel_or_thread(snowflake):
                resolved.append(g)  # type: ignore
            if g := ctx.guild.get_role(snowflake):
                resolved.append(g)
            if g := ctx.guild.get_member(snowflake):
                resolved.append(g)
            unresolved.append(snowflake)

        if unresolved:
            await self.bot.api.bulk_upsert_guild_automod_default_ignores(ctx.guild.id, [x.id for x in resolved])
            await self.get_automod_config.invalidate(ctx.guild.id)

        return resolved

    @automod.command(level=CommandLevel.Admin, name='ignored')
    @is_server_manager()
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

        resolved = await self.verify_default_ignores(ctx, config['default_ignores'])

        pages = Paginator(ui.AutoModIgnoredPages([r.mention for r in resolved],
                          per_page=10), context=ctx)
        await pages.start()

    @automod.group(level=CommandLevel.Admin, name='rules')
    @is_server_manager()
    async def automod_rules(self, ctx: GuildContext):
        ...

    @automod_rules.command(level=CommandLevel.Admin, name="add")
    @is_server_manager()
    @app_commands.describe(rule="The AutoMod rule to set up",
                           interval="The interval of when the rule should be triggered, i.e. 5/10s",
                           punishment="The punishment when the user goes over the limit",
                           punishment_duration="The duration to set for the punishment's mute or ban")
    @app_commands.choices(rule=[app_commands.Choice(name=x,
                                                    value=y) for y, x in AUTOMOD_ADVANCED_EVENT_NAMES_MAPPING.items()],
                          punishment=[app_commands.Choice(name=x.name.capitalize(),
                                                          value=x.name.lower()) for x in AutoModPunishmentType])
    async def add_automod_rules(self, ctx: GuildContext, rule: AUTOMOD_EVENT_NAMES_LITERAL,
                                interval: Annotated[AutoModDurationResponse, AutoModDuration],
                                punishment: Literal['delete', 'warn', 'mute', 'kick', 'ban'],  # type: ignore
                                punishment_duration: Optional[ShortTime] = None):
        """Adds a new rule to AutoMod.

        You can provide the interval in the following ways
        To set automod to do something at 5 messages per 10 seconds, you can express it in one of the following ways
        - "5/10s"
        - "5 10"
        """
        punishment: AutoModPunishmentType = AutoModPunishmentType[punishment.upper()]
        punishment_payload: Dict[str, Any] = {"type": punishment.name}

        if punishment.name in ("BAN", "MUTE") and punishment_duration:
            punishment_payload['duration'] = punishment_duration.delta.seconds

        payload = {"guild_id": ctx.guild.id,
                   "type": rule,
                   "count": interval.count,
                   "seconds": interval.seconds,
                   "punishment": punishment_payload}
        try:
            await self.bot.api.create_guild_automod_rule(ctx.guild.id, payload)
        except DataConflict:
            await ctx.reply("This rule has already been set up!\nIf you want to edit this rule, please remove it and"
                            " then re-run this command again!")
            return

        await ctx.reply(f"Successfully set up {AUTOMOD_EVENT_NAMES_MAPPING[rule]}!")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod_rules.command(level=CommandLevel.Admin, name="addbasic")
    @is_server_manager()
    @app_commands.describe(rule="The AutoMod rule to add")
    @app_commands.choices(rule=[app_commands.Choice(name=x,
                                                    value=y) for y, x in AUTOMOD_BASIC_EVENT_NAMES_MAPPING.items()])
    async def add_basic_automod_rule(self, ctx: GuildContext, rule: AUTOMOD_BASIC_EVENTS_LITERAL):
        """Adds a new basic rule to AutoMod"""
        payload = {"guild_id": ctx.guild.id,
                   "type": rule,
                   "count": 0,
                   "seconds": 0}

        try:
            await self.bot.api.create_guild_automod_rule(ctx.guild.id, payload)
        except DataConflict:
            await ctx.reply("This rule has already been set up!\nIf you want to edit this rule, please remove it and"
                            " then re-run this command again!")
            return

        await ctx.reply(f'Successfully set up {AUTOMOD_EVENT_NAMES_MAPPING[rule]}!')
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod_rules.command(level=CommandLevel.Admin, name="remove")
    @is_server_manager()
    @app_commands.describe(rule="The AutoMod rule to remove")
    @app_commands.choices(rule=[app_commands.Choice(name=x, value=y) for y, x in AUTOMOD_EVENT_NAMES_MAPPING.items()])
    async def remove_automod_rule(self, ctx: GuildContext, rule: AUTOMOD_ALL_EVENT_NAMES_LITERAL):
        """Removes an existing AutoMod rule"""
        try:
            await self.bot.api.delete_guild_automod_rule(ctx.guild.id, rule)
        except NotFound:
            await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was never set up!")
            return

        await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was removed.")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod.group(name='warnthreshold', level=CommandLevel.Admin)
    @is_server_manager()
    async def automod_warn_threshold(self, ctx: GuildContext):
        """Manages the threshold for warns"""
        ...

    async def set_warn_threshold(self, guild: discord.Guild, limit: int, punishment: str):
        query = """INSERT INTO guild_automod_config (guild_id, warn_threshold, warn_punishment)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET
                       warn_threshold=EXCLUDED.warn_threshold,
                       warn_punishment=EXCLUDED.warn_punishment;"""
        await self.bot.pool.execute(query, guild.id, limit, punishment.upper())

    @automod_warn_threshold.command(name='set', level=CommandLevel.Admin)
    @is_server_manager()
    @app_commands.describe(limit="The limit of warns")
    async def automod_warn_threshold_set(self, ctx: GuildContext, limit: commands.Range[int, 1, 10],
                                         punishment: Literal['kick', 'ban']):
        """Sets a threshold for warns"""
        await self.set_warn_threshold(ctx.guild, limit, punishment)
        await ctx.send(f"Set the warn threshold to {limit}!")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod_warn_threshold.command(name='migrate', level=CommandLevel.Admin)
    @is_server_manager()
    async def automod_warn_threshold_transfer(self, ctx: GuildContext):
        """Migrates your server's old warn punishment configuration to the new configuration"""
        cog: Optional[Moderation] = self.bot.get_cog("Moderation")  # type: ignore
        if not cog:
            await ctx.send("Unable to migrate warn thresholds at this time!")
            return

        record = await cog.get_mod_config(ctx.guild.id)
        if not record or (record.warn_ban is None and record.warn_kick is None):
            await ctx.send("There is nothing to migrate!")
            return

        if record.warn_ban and record.warn_kick:
            view = ui.AutoModWarnThresholdMigration(author_id=ctx.author.id)
            await ctx.send("Which would you like to migrate?\n\n> *Warn thresholds only support one threshold!*",
                           view=view)
            await view.wait()
            if not view.choice:
                await ctx.reply("You didn't select anything! Exiting...")
                return

            limit = getattr(record, view.choice)
            punishment = view.choice[5:]
        elif record.warn_ban:
            limit = record.warn_ban
            punishment = "ban"
        elif record.warn_kick:
            limit = record.warn_kick
            punishment = "kick"

        await self.set_warn_threshold(ctx.guild, limit, punishment)

        # Remove old configuration
        query = "UPDATE guild_mod_config SET warn_ban=NULL, warn_kick=NULL WHERE guild_id=$1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        await cog.get_mod_config.invalidate(ctx.guild.id)

        await ctx.send("Migrated to the new warn thresholds!")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod_warn_threshold.command(name='remove', level=CommandLevel.Admin)
    @is_server_manager()
    async def automod_warn_threshold_remove(self, ctx: GuildContext):
        """Removes the current warn threshold"""
        query = "UPDATE guild_automod_config SET warn_threshold=NULL, warn_punishment=NULL WHERE guild_id=$1;"
        resp = await self.bot.pool.execute(query, ctx.guild.id)

        if resp == "UPDATE 0":
            await ctx.send("This server never had a warn threshold set up!")
            return

        await ctx.send("Removed warn threshold!")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @cache.cached('guild_automod', cache.Strategy.raw)
    async def get_automod_config(self, guild_id: int) -> Optional[AutomodConfig]:
        try:
            config = await self.bot.api.get_guild_automod_config(guild_id)
        except NotFound:
            return

        return AutomodConfig(self.bot, config)

    async def add_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> str:
        return await self.bot.get_cog("Moderation").add_punishment_role(guild_id, user_id, role_id,
                                                                        connection=connection)

    async def remove_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> None:
        return await self.bot.get_cog("Moderation").remove_punishment_role(guild_id, user_id, role_id,
                                                                           connection=connection)

    async def log_manual_action(self, guild: discord.Guild, target, moderator,
                                action: Union[ActionType, str], *, timestamp=None,
                                reason: Optional[str] = None, **kwargs) -> None:
        # We need this for bulk actions
        c: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        return await c.log_manual_action(guild, target, moderator, action, timestamp=timestamp, reason=reason, **kwargs)

    async def is_member_whitelisted(self, message: discord.Message) -> bool:
        """Check that tells whether a member is exempt from automod or not"""
        # TODO: Check against a generic set of moderator permissions.
        record = await self.bot.get_guild_bot_config(message.guild.id)
        if not record or record.permissions is None:
            return False

        if record.permissions.levels is None:
            level = CommandLevel.User
        else:
            roles = message.author._roles if hasattr(message.author, "_roles") else []
            level = record.permissions.levels.get_user_level(message.author.id, roles)

        if level == CommandLevel.Blocked:  # Blocked to commands, not ignored by automod
            return False

        return level.value >= CommandLevel.Trusted.value

    # These only require one param, "message", because it contains all the information we want.
    async def _warn_punishment(self, message: AutoModMessage, *, reason):
        await self.log_manual_action(message.guild, message.author, self.bot.user, "WARN", reason=reason)

    # Change reason
    async def _kick_punishment(self, message: AutoModMessage, *, reason):
        await message.author.kick(reason=reason)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "KICK",
                                     reason=reason)

    async def _time_ban_member(self, message: AutoModMessage, seconds: Union[int, datetime.datetime], *, reason):
        if isinstance(seconds, datetime.datetime):
            duration = seconds
        else:
            duration = message.created_at + datetime.timedelta(seconds=seconds)

        cog: Reminders = self.bot.get_cog("Reminders")  # type: ignore
        timer_id = await cog.add_timer("timeban", message.created_at, duration, guild_id=message.guild.id,
                                       user_id=message.author.id, mod_id=self.bot.user.id, force_insert=True,
                                       timezone=duration.tzinfo or datetime.timezone.utc)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEBAN", expiry=duration,
                                     timer_id=timer_id, reason=reason)

    async def _ban_punishment(self, message: AutoModMessage, duration=None, *, reason):
        await message.author.ban(reason=reason)
        if duration:
            await self._time_ban_member(message, duration, reason=reason)
            return
        await self.log_manual_action(message.guild, message.author, self.bot.user, "BAN", reason=reason)

    async def _delete_punishment(self, message: discord.Message, **kwargs):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def get_mute_role(self, guild_id: int):
        cog: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        cfg = await cog.get_mod_config(guild_id)
        if not cfg:
            # No mute role... Perhaps a bot log channel would be helpful to guilds...
            return

        guild = self.bot.get_guild(guild_id)
        if not cfg.mute_role_id:
            return

        return guild.get_role(cfg.mute_role_id)

    def can_timeout(self, message: AutoModMessage, duration: datetime.datetime):
        """Determines whether the bot can timeout a member.

        Parameters
        ----------
        message : AutoModMessage
            The message
        duration : datetime.datetime
            An instance of datetime.datetime

        Returns
        -------
        bool
            Returns True if the bot can timeout a member
        """
        me = message.guild.me
        return bool(
            message.channel.permissions_for(me).moderate_members
            and duration <= (message.created_at + datetime.timedelta(days=28))  # noqa: W503
        )

    async def _time_mute_user(self, message: AutoModMessage, seconds: Union[int, datetime.datetime], *, reason: str):
        if isinstance(seconds, datetime.datetime):
            duration = seconds
        else:
            duration = message.created_at + datetime.timedelta(seconds=seconds)

        if self.can_timeout(message, duration):
            await message.author.edit(timed_out_until=duration, reason=reason)
            return

        role = await self.get_mute_role(message.guild.id)
        if not role:
            # Report something went wrong...
            return

        if not message.channel.permissions_for(message.guild.me).manage_roles:
            return

        cog: Reminders = self.bot.get_cog('Reminders')  # type: ignore
        job_id = await cog.add_timer("timemute", message.created_at, duration,
                                     guild_id=message.guild.id, user_id=message.author.id, role_id=role.id,
                                     mod_id=self.bot.user.id, force_insert=True,
                                     timezone=duration.tzinfo or datetime.timezone.utc)
        await message.author.add_roles(role, reason=reason)

        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEMUTE",
                                     reason="Member triggered automod", expiry=duration, timer_id=job_id,
                                     timestamp=message.created_at)

    async def _mute_punishment(self, message: AutoModMessage, duration=None, *, reason: str):
        if duration:
            return await self._time_mute_user(message, duration, reason=reason)

        if not message.channel.permissions_for(message.guild.me).manage_roles:
            return

        role = await self.get_mute_role(message.guild.id)
        if not role:
            return

        await message.author.add_roles(role, reason=reason)
        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "MUTE",
                                     reason=reason, timestamp=message.created_at)

    punishments = {"WARN": _warn_punishment,
                   "KICK": _kick_punishment,
                   "BAN": _ban_punishment,
                   "DELETE": _delete_punishment,
                   "MUTE": _mute_punishment
                   }

    async def _handle_punishment(self, options: GuildAutoModRulePunishment, message: discord.Message,
                                 automod_rule_name: str):
        automod_rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(automod_rule_name.replace('_', '-'), "AutoMod rule")
        reason = f"{automod_rule_name} triggered"

        meth = self.punishments[str(options.type)]

        if options.type not in ("MUTE", "BAN"):
            await meth(self, message, reason=reason)
            return

        await meth(self, message, options.duration, reason=reason)

    async def _delete_tracked_messages(self, messages: set[str], guild: discord.Guild):
        # Deletes message IDs tracked in AutoMod
        tmp: Dict[str, List[discord.Object]] = {}
        for message in messages:
            channel_id, message_id = message.split(":")
            if channel_id not in tmp:
                tmp[channel_id] = [discord.Object(message_id)]
            else:
                tmp[channel_id].append(discord.Object(message_id))

        for channel_id, message_ids in tmp.items():
            channel = guild.get_channel_or_thread(int(channel_id))
            if not channel:
                continue

            with contextlib.suppress(discord.HTTPException):
                await channel.delete_messages(message_ids, reason="Clean up of recent AutoMod trigger")

    async def check_message(self, message: discord.Message, config: AutomodConfig):
        async def handle_bucket(attr_name: str, increment: Optional[Callable[[discord.Message], int]] = None):
            obj: Optional[SpamConfig] = getattr(config, attr_name, None)
            if not obj:
                return

            # We would handle rule specific ignores here but that's not applicable at this time.

            if increment:
                rl = await obj.update_bucket(message, increment(message))
            else:
                rl = await obj.update_bucket(message)

            if rl is True:
                messages = await obj.fetch_responsible_messages(message)
                await obj.reset_bucket(message)
                await self._handle_punishment(obj.punishment, message, attr_name)
                if obj.punishment.type != "BAN":
                    await self._delete_tracked_messages(messages, message.guild)

        await handle_bucket('mass_mentions', lambda m: len(m.mentions) + len(m.role_mentions))
        await handle_bucket('message_spam')
        await handle_bucket('message_content_spam')
        await handle_bucket('invite_spam')
        await handle_bucket('url_spam')

    @LightningCog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:  # DM Channels are exempt.
            return

        # Ignore system content
        if message.is_system():
            return

        # Ignore bots (for now)
        if message.author.bot:
            return

        # Ignore higher ups
        if hasattr(message.author, 'top_role') and message.guild.me.top_role < message.author.top_role:
            return

        check = await self.is_member_whitelisted(message)
        if check is True:
            return

        record = await self.get_automod_config(message.guild.id)
        if not record:
            return

        if record.is_ignored(message):
            return

        await self.check_message(message, record)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_automod_config.invalidate(guild.id)

    async def handle_name_changing(self, member: discord.Member, record: AutomodConfig):
        if record.auto_normalize is False and record.auto_dehoist is False:
            return

        if record.auto_normalize is True and record.auto_dehoist is False:
            try:
                await member.edit(nick=unidecode(member.display_name), reason="Auto normalize")
            except discord.HTTPException:
                pass

        cog: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        await cog.dehoist_member(member, self.bot.user, COMMON_HOIST_CHARACTERS, normalize=record.auto_normalize)

    @LightningCog.listener()
    async def on_member_join(self, member: discord.Member):
        record = await self.get_automod_config(member.guild.id)
        if not record:
            return

        await self.handle_name_changing(member, record)

    @LightningCog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name == after.display_name:
            return

        record = await self.get_automod_config(after.guild.id)
        if not record:
            return

        await self.handle_name_changing(after, record)

    async def get_warn_count(self, guild_id: int, user_id: int) -> int:
        query = "SELECT COUNT(*) FROM infractions WHERE user_id=$1 AND guild_id=$2 AND action=$3;"
        rev = await self.bot.pool.fetchval(query, user_id, guild_id,
                                           ActionType.WARN.value)
        return rev or 0

    # Warn Thresholds
    @LightningCog.listener('on_lightning_member_warn')
    async def handle_warn_thresholds(self, event: InfractionEvent):
        record = await self.get_automod_config(event.guild.id)

        if not record or not record.warn_threshold:
            return

        count = await self.get_warn_count(event.guild.id, event.member.id)

        if record.warn_threshold > count:
            return

        if record.warn_punishment.lower() == "kick":
            await event.guild.kick(event.member, reason="Warn Threshold reached")
        else:  # ban
            await event.guild.ban(event.member, reason="Warn Threshold reached", delete_message_days=0)

        await self.log_manual_action(event.guild, event.member, self.bot.user, record.warn_punishment.upper(),
                                     reason="Warn Threshold reached")

    # Remove ids from config
    @LightningCog.listener('on_member_remove')
    @LightningCog.listener('on_guild_channel_delete')
    @LightningCog.listener('on_guild_role_delete')
    @LightningCog.listener('on_thread_delete')
    async def on_snowflake_removal(self, payload):
        # payload: Union[discord.Member, discord.Role, discord.abc.GuildChannel, discord.Thread]
        config = await self.get_automod_config(payload.guild.id)
        if not config:
            return

        try:
            config.default_ignores.remove(payload.id)
        except KeyError:
            return

        await self.bot.api.bulk_upsert_guild_automod_default_ignores(payload.guild.id, config.default_ignores)
