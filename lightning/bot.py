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

import asyncio
import collections
import contextlib
import logging
import pathlib
import secrets
import sys
import traceback
from datetime import datetime
from typing import List, Optional, Union

import aiohttp
import asyncpg
import discord
import redis.asyncio as aioredis
import sentry_sdk
from discord import app_commands
from discord.ext import commands, menus
from sanctum import HTTPClient

from lightning import cache, errors
from lightning.config import Config
from lightning.context import LightningContext
from lightning.meta import __version__ as version
from lightning.models import GuildBotConfig
from lightning.storage import Storage
from lightning.utils.emitters import WebhookEmbedEmitter

__all__ = ("LightningBot", )
log = logging.getLogger(__name__)


ERROR_HANDLER_MESSAGES = {
    commands.NoPrivateMessage: "This command cannot be used in DMs!",
    commands.DisabledCommand: "Sorry, this command is currently disabled.",
    commands.NSFWChannelRequired: "This command can only be run in a NSFW marked channel or DMs.",
    asyncio.TimeoutError: "Timed out while doing something..."
}


async def _callable_prefix(bot: LightningBot, message: discord.Message):
    if bot.config.bot.beta_prefix:
        return bot.config.bot.beta_prefix

    prefixes = [f'<@!{bot.user.id}> ', f'<@{bot.user.id}> ']
    if message.guild is None:
        generic_defaults = ['!', '.', '?']
        return prefixes + generic_defaults

    record = await bot.get_guild_bot_config(message.guild.id)
    prefix = getattr(record, "prefixes", None)

    if prefix:
        prefixes.extend(prefix)

    return prefixes


class Tree(app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError, /) -> None:
        command = interaction.command
        if not command:
            return await super().on_error(interaction, error)

        if command._has_any_error_handlers():
            return

        if interaction.response.is_done():
            messagable = interaction.followup.send
        else:
            messagable = interaction.response.send_message

        if isinstance(error, app_commands.MissingPermissions):
            p = ', '.join(error.missing_permissions).replace('_', ' ').replace('guild', 'server').title()
            await messagable(f"You are missing {p} permissions to use this command!", ephemeral=True)
            return

        return await super().on_error(interaction, error)


class LightningBot(commands.AutoShardedBot):
    pool: asyncpg.Pool
    redis_pool: aioredis.Redis
    api: HTTPClient
    aiosession: aiohttp.ClientSession
    user: discord.ClientUser

    def __init__(self, config: Config, **kwargs):
        intents = discord.Intents.all()
        intents.presences = False
        intents.invites = False
        intents.voice_states = False

        super().__init__(command_prefix=_callable_prefix, reconnect=True,
                         allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False),
                         intents=intents, tree_cls=Tree, **kwargs)

        self.launch_time = discord.utils.utcnow()

        self.command_spammers = collections.Counter()
        # This should be good enough
        self.command_spam_cooldown = commands.CooldownMapping.from_cooldown(6, 5.0, commands.BucketType.user)

        self.config: Config = config
        self.version = version
        self._pending_cogs = {}

        self.blacklisted_users = Storage("config/user_blacklist.json")

    async def load_cogs(self) -> None:
        def _transform_path(p):
            return str(p).replace("/", ".").replace("\\", ".")

        path = pathlib.Path("lightning/cogs/")
        cog_list = []

        # "Plugin" handling
        for plugin in path.glob("*/__init__.py"):
            cog_list.append(_transform_path(plugin.parent))

        for name in path.glob("**/*.py"):
            qual_name = _transform_path(name.with_suffix(""))
            if _transform_path(name.parent) in cog_list:
                log.debug(f"Skipping over {str(name)}...")
                continue

            cog_list.append(qual_name)

        for cog in cog_list:
            if cog in self.config.bot.disabled_cogs:
                continue

            try:
                await self.load_extension(cog)
            except Exception as e:
                log.error(f"Failed to load {cog}", exc_info=e)

    async def setup_hook(self):
        self.api = HTTPClient(self.config.tokens.api.url, self.config.tokens.api.key)

        if self.config.bot.user_agent:
            headers = {"User-Agent": self.config.bot.user_agent}
        else:
            headers = {"User-Agent": f"Lightning Discord Bot/{self.version}"}
        self.aiosession = aiohttp.ClientSession(headers=headers)

        await self.load_cogs()
        # Error logger
        self._error_logger = WebhookEmbedEmitter(self.config.logging.bot_errors, session=self.aiosession)
        self._error_logger.start()

    @cache.cached('guild_bot_config', cache.Strategy.lru, max_size=128)
    async def get_guild_bot_config(self, guild_id: int) -> Optional[GuildBotConfig]:
        """Gets a guild's bot configuration from cache or fetches it from the database.

        Parameters
        ----------
        guild_id : int
            The guild's ID to fetch

        Returns
        -------
        Optional[GuildBotConfig]
            The guild's bot configuration or None
        """
        query = """SELECT * FROM guild_config WHERE guild_id=$1;"""
        record = await self.pool.fetchrow(query, guild_id)
        return GuildBotConfig(self, record) if record else None

    async def add_cog(self, cls: commands.Cog, /, *, override: bool = False, guild=discord.utils.MISSING,
                      guilds=discord.utils.MISSING) -> None:
        deps = getattr(cls, "__lightning_cog_deps__", None)
        if not deps:
            log.debug(f"Loaded cog {cls.__module__} ({cls})")
            await super().add_cog(cls, override=override, guild=guild, guilds=guilds)
            return

        required_cogs = [self.get_cog(name) for name in deps.required]
        if not all(required_cogs):
            if hasattr(cls, '__name__'):
                self._pending_cogs[cls.__name__] = cls
            else:
                self._pending_cogs[cls.__class__.__name__] = cls
            return

        await super().add_cog(cls, override=override, guild=guild, guilds=guilds)
        log.debug(f"Loaded LightningCog {cls.__module__} ({cls}).")

        # Try loading cogs pending
        pending_cogs = self._pending_cogs
        self._pending_cogs = {}
        for cog in list(pending_cogs.values()):
            log.debug(f"Trying to load {cog.__module__} ({str(cog)})")
            await self.add_cog(cog)

    async def on_ready(self) -> None:
        summary = f"{len(self.guilds)} guild(s) and {len(self.users)} user(s)"
        log.info(f'READY: {str(self.user)} ({self.user.id}) and can see {summary}.')

    async def _notify_of_spam(self, member, channel, guild=None, blacklist=False) -> None:
        e = discord.Embed(color=discord.Color.red(), title="Member hit ratelimit", timestamp=discord.utils.utcnow())
        webhook = discord.Webhook.from_url(self.config.logging.blacklist_alerts, session=self.aiosession)

        if blacklist:
            log.info(f"User automatically blacklisted for command spam | {member} | ID: {member.id}")
            e.title = "Automatic Blacklist"

        e.description = f"Spam Count: {self.command_spammers[member.id]}/5"
        done_fmt = f'__Channel__: {channel} (ID: {channel.id})'
        if guild:
            done_fmt = f'{done_fmt}\n__Guild__: {guild} (ID: {guild.id})'
        e.add_field(name="Location", value=done_fmt)
        e.add_field(name="User", value=f"{str(member)} (ID: {member.id})")
        await webhook.send(embed=e)

    @property
    def owners(self) -> List[int]:
        return [self.owner_id] if self.owner_id else self.owner_ids

    async def auto_blacklist_check(self, message: discord.Message) -> None:
        author = message.author.id
        if await self.is_owner(message.author):
            return

        bucket = self.command_spam_cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            # User hit the ratelimit
            self.command_spammers[author] += 1
            if self.command_spammers[author] >= self.config.bot.spam_count:
                await self.blacklisted_users.add(author, "Automatic blacklist on command spam")
                await self._notify_of_spam(message.author, message.channel, message.guild, True)
            else:
                # Notify of hitting the ratelimit
                await self._notify_of_spam(message.author, message.channel, message.guild)
                log.debug(f"User {message.author} ({author}) hit the command ratelimit")
        else:
            del self.command_spammers[author]

    async def get_context(self, message: Union[discord.Message, discord.Interaction], *, cls=LightningContext):
        return await super().get_context(message, cls=cls)

    async def process_command_usage(self, message):
        if str(message.author.id) in self.blacklisted_users:
            return

        ctx = await self.get_context(message)
        if ctx.command is None:
            return

        await self.auto_blacklist_check(message)
        await self.invoke(ctx)

    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_command_usage(message)

    async def on_message_edit(self, before, after):
        if not self.config.bot.edit_commands:
            return

        if before.content != after.content:
            await self.on_message(after)

    async def on_command(self, ctx: LightningContext):
        fmt = [f"{ctx.message.author} ({ctx.message.author.id}): "]

        if ctx.message.content:
            fmt.append(f"\"{ctx.message.content}\" ")
        else:
            if vars(ctx.interaction.namespace):
                fmt.append(f"\"/{ctx.command.qualified_name} {vars(ctx.interaction.namespace)}\" ")
            else:
                fmt.append(f"\"{ctx.command.qualified_name}\" ")

        if ctx.guild:
            fmt.append(f"in \"{ctx.channel.name}\" ({ctx.channel.id}) "
                       f"at \"{ctx.guild.name}\" ({ctx.guild.id})")
        else:
            fmt.append(f"in DMs ({ctx.channel.id})")

        log.info(''.join(fmt))

    def can_log_bugs(self) -> bool:
        return bool(self.config.tokens.sentry)

    async def on_error(self, event: str, *args, **kwargs):
        exc = sys.exc_info()

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)
            log.exception(f"Error on {event}", exc_info=exc)

        exc = ''.join(traceback.format_exception(exc[0], exc[1], exc[2], chain=False))
        if len(exc) >= 2040:
            resp = await self.api.create_paste(exc)
            desc = f"Traceback too long...\n{resp['full_url']}"
        else:
            desc = f"```py\n{exc}```"

        embed = discord.Embed(title="Event Error", description=desc,
                              color=discord.Color.gold(),
                              timestamp=discord.utils.utcnow())
        embed.add_field(name="Event", value=event)
        if args:
            embed.add_field(name="Args", value=", ".join(repr(arg) for arg in args))
        if kwargs:
            embed.add_field(name="Kwargs", value=", ".join(repr(arg) for arg in kwargs))
        await self._error_logger.put(embed)

    async def log_command_error(self, ctx: LightningContext, error, *, send_error_message=True) -> str:
        """Inserts a command error into the database.

        Parameters
        ----------
        ctx : LightningContext
            The context
        error : Exception
            The error from the command
        send_error_message : bool, optional
            Whether the bot should send an message back with the bug token, by default True

        Returns
        -------
        str
            The newly created bug's token
        """
        error = error.original if hasattr(error, 'original') else error
        token = secrets.token_hex(6)
        lines = traceback.format_exception(type(error), error, error.__traceback__, chain=False)
        traceback_text = ''.join(lines)
        query = """INSERT INTO command_bugs (token, traceback, created_at)
                   VALUES ($1, $2, $3);
                """
        await self.pool.execute(query, token, traceback_text, datetime.utcnow())

        if send_error_message:
            with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                await ctx.send(f"\N{BUG} An unexpected error occurred. `{token}`")

        return token

    async def on_command_error(self, ctx: LightningContext, error: Exception) -> None:

        # Check if command has an error handler first
        if ctx.command.has_error_handler():
            return
        # Check if cog has an error handler after
        if hasattr(ctx, 'cog'):
            assert ctx.cog is not None

            if ctx.cog.has_error_handler():
                return

        error = getattr(error, "original", error)
        error_text = str(error)

        # Generic error handler messages
        handled = ERROR_HANDLER_MESSAGES.get(type(error), None)
        if handled:
            await ctx.send(handled)
            return

        if isinstance(error, commands.BotMissingPermissions):
            p = ', '.join(error.missing_permissions).replace('_', ' ').replace('guild', 'server').title()
            await ctx.send("I don't have the right permissions to run this command. "
                           f"I need: {p}")
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send("You are currently on cooldown. Try the command again in "
                           f"{error.retry_after:.1f} seconds.")
            return
        help_text = f"\nPlease see `{ctx.prefix}help {ctx.command}` for more info about this command."
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"You gave incorrect arguments. `{str(error)}` {help_text}", suppress_embeds=True)
            return
        elif isinstance(error, (commands.MissingRequiredArgument, errors.MissingRequiredFlagArgument)):
            codeblock = f"**{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}**\n\n{error_text}"
            await ctx.send(codeblock)
            return
        elif isinstance(error, commands.TooManyArguments):
            await ctx.send(f"You passed too many arguments.{help_text}")
            return
        elif isinstance(error, commands.BadLiteralArgument):
            lts = ', '.join(f'\"{e}\"' for e in error.literals)
            await ctx.send(f"You gave an incorrect argument for {error.param.name}. I expected one of "
                           f"{lts}.\n> **These are case sensitive!**")
            return
        elif isinstance(error, (errors.LightningError, errors.FlagError, menus.MenuError, commands.UserInputError)):
            await ctx.send(error_text)
            return

        # Errors that should give no output.
        if isinstance(error, (commands.NotOwner, commands.CommandNotFound,
                              commands.CheckFailure)):
            return

        with sentry_sdk.push_scope() as scope:
            scope.user = {"id": ctx.author.id, "username": str(ctx.author)}
            scope.set_tag("command", ctx.command.qualified_name)
            scope.set_extra("message content", ctx.message.content)
            log.error(f"An exception occurred with {type(error)}", exc_info=error)

        embed = discord.Embed(title='Command Error', color=0xff0000,
                              timestamp=discord.utils.utcnow())
        embed.add_field(name='Name', value=ctx.command.qualified_name)
        embed.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        donefmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            donefmt = f'{donefmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'
        embed.add_field(name='Location', value=donefmt, inline=False)

        if self.can_log_bugs():
            token = await self.log_command_error(ctx, error)
            embed.add_field(name='Bug Token', value=token)

        await self._error_logger.put(embed)

    async def close(self) -> None:
        log.info("Shutting down...")
        log.info("Closing database...")
        await self.pool.close()
        await self.aiosession.close()
        await self.api.close()
        log.info("Closed aiohttp session and database successfully.")
        await self.redis_pool.connection_pool.disconnect()
        await super().close()
