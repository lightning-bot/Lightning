"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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

import datetime
from typing import (TYPE_CHECKING, Any, Callable, Dict, List, Literal,
                    Optional, TypedDict, Union)

import discord
from discord import app_commands
from discord.ext import commands
from sanctum.exceptions import DataConflict, NotFound

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, cache, hybrid_group)
from lightning.cogs.automod import ui
from lightning.cogs.automod.converters import (AutoModDuration,
                                               AutoModDurationResponse,
                                               IgnorableEntities)
from lightning.cogs.automod.models import AutomodConfig, SpamConfig
from lightning.constants import (AUTOMOD_EVENT_NAMES_LITERAL,
                                 AUTOMOD_EVENT_NAMES_MAPPING,
                                 COMMON_HOIST_CHARACTERS)
from lightning.enums import ActionType
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
        # AutoMod stats?

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
            rules = await ctx.bot.api.get_guild_automod_rules(ctx.guild.id)
        except NotFound:
            await ctx.send("This server has not set up Lightning AutoMod yet!")
            return

        fmt = []
        for record in rules:
            if record['type'] == "mass-mentions":
                fmt.append(f"{AUTOMOD_EVENT_NAMES_MAPPING[record['type']]}: {record['count']}")
            else:
                fmt.append(f"{AUTOMOD_EVENT_NAMES_MAPPING[record['type']]}: {record['count']}/{record['seconds']}s")

        embed = discord.Embed(color=0xf74b06, title="Lightning AutoMod")
        embed.add_field(name="Rules", value="\n".join(fmt))

        try:
            config = await self.bot.api.get_guild_automod_config(ctx.guild.id)
        except NotFound:
            config = {}

        if default_ignores := config.get("default_ignores"):
            ignores = await self.verify_default_ignores(ctx, default_ignores)
            fmt = "\n".join(x.mention for x in ignores[:10])
            if len(ignores) > 10:
                fmt = f"{fmt}\n and {len(ignores) - 10} more..."
            embed.add_field(name="Ignores", value=fmt)
        else:
            embed.add_field(name="Ignores", value="None")

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
    @app_commands.describe(type="The AutoMod rule to set up",
                           interval="The interval of when the rule should be triggered")
    async def add_automod_rules(self, ctx: GuildContext, type: AUTOMOD_EVENT_NAMES_LITERAL,
                                *, interval: str):
        """Adds a new rule to AutoMod.

        You can provide the interval in the following ways
        To set automod to do something at 5 messages per 10 seconds, you can express it in one of the following ways
        - "5/10s"
        - "5 10"
        """
        if type == "mass-mentions":
            try:
                result = AutoModDurationResponse(int(interval), 0)
            except ValueError:
                await ctx.send("Could not convert to an integer")
                return
        else:
            result: AutoModDurationResponse = await AutoModDuration().convert(ctx, interval)

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
            await ctx.reply("This rule has already been set up!\nIf you want to edit this rule, please remove it and"
                            " then re-run this command again!")
            return

        await ctx.reply(f"Successfully set up {AUTOMOD_EVENT_NAMES_MAPPING[type]}!")
        await self.get_automod_config.invalidate(ctx.guild.id)

    @automod_rules.command(level=CommandLevel.Admin, name="remove")
    @is_server_manager()
    @app_commands.describe(rule="The AutoMod rule to remove")
    async def remove_automod_rule(self, ctx: GuildContext, rule: AUTOMOD_EVENT_NAMES_LITERAL):
        """Removes an existing automod rule"""
        try:
            await self.bot.api.delete_guild_automod_rule(ctx.guild.id, rule)
        except NotFound:
            await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was never set up!")
            return

        await ctx.send(f"{AUTOMOD_EVENT_NAMES_MAPPING[rule]} was removed.")
        await self.get_automod_config.invalidate(ctx.guild.id)

    # @automod_rules.command(level=CommandLevel.Admin, name="sync", enabled=False, hidden=True)
    @is_server_manager()
    async def sync_automod_rule(self, ctx: GuildContext, rule: Literal['mass-mentions']):
        """
        "Syncs" an AutoMod rule with Discord's AutoMod
        """
        try:
            await self.bot.api.get_guild_automod_rules(ctx.guild.id)
        except NotFound:
            await ctx.send("No AutoMod rules are set up for this server!")
            return

    @cache.cached('guild_automod', cache.Strategy.raw)
    async def get_automod_config(self, guild_id: int) -> Optional[AutomodConfig]:
        try:
            config = await self.bot.api.get_guild_automod_config(guild_id)
            rules = await self.bot.api.get_guild_automod_rules(guild_id)
        except NotFound:
            rules = None

            if not rules:
                return

            config = {"guild_id": guild_id}

        return AutomodConfig(self.bot, config, rules) if rules else None

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
                                       user_id=message.author.id, mod_id=self.bot.user.id, force_insert=True)
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
        if message.channel.permissions_for(me).moderate_members and \
                duration <= (message.created_at + datetime.timedelta(days=28)):
            return True
        return False

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
                                     mod_id=self.bot.user.id, force_insert=True)
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
                await obj.reset_bucket(message)
                await self._handle_punishment(obj.punishment, message, attr_name)

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

    @LightningCog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.name == after.name:
            return

        record = await self.get_automod_config(after.guild.id)
        if not record:
            return

        if not record.auto_dehoist:
            return

        cog: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        await cog.dehoist_member(after, self.bot.user, COMMON_HOIST_CHARACTERS)

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
