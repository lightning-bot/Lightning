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

import asyncio
import collections
import contextlib
import json
import logging
import pathlib
import secrets
import traceback
from datetime import datetime
from typing import Optional

import aiohttp
import asyncpg
import discord
import sentry_sdk
from discord.ext import commands, menus

from lightning import cache, config, errors
from lightning.context import LightningContext
from lightning.meta import __version__ as version
from lightning.models import CommandOverrides, GuildPermissions

log = logging.getLogger(__name__)


ERROR_HANDLER_MESSAGES = {
    commands.NoPrivateMessage: "This command cannot be used in DMs!",
    commands.DisabledCommand: "Sorry, this command is currently disabled.",
    commands.NSFWChannelRequired: "This command can only be run in a NSFW marked channel or DMs.",
    asyncio.TimeoutError: "Timed out while doing something..."
}


async def _callable_prefix(bot, message):
    beta_prefix = bot.config['bot'].get("beta_prefix", None)
    if beta_prefix:
        return beta_prefix

    prefixes = [f'<@!{bot.user.id}> ', f'<@{bot.user.id}> ']
    if message.guild is None:
        prefixes.append(".")
        return prefixes

    cached = await bot.prefixes.get_or_default(message.guild.id)
    if cached:
        prefixes.extend(cached)
        return prefixes
    else:
        ret = await bot.pool.fetchval("SELECT prefix FROM guild_config WHERE guild_id=$1", message.guild.id) or None
        await bot.prefixes.set(message.guild.id, ret)
        if ret:
            prefixes.extend(ret)
        return prefixes


class LightningBot(commands.AutoShardedBot):
    def __init__(self):
        # Intents stuff
        intents = discord.Intents.all()
        intents.invites = False
        intents.voice_states = False
        super().__init__(command_prefix=_callable_prefix, reconnect=True,
                         allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False),
                         member_cache_flags=discord.MemberCacheFlags(online=True, voice=False, joined=True),
                         intents=intents)
        self.launch_time = datetime.utcnow()

        self.command_spammers = collections.Counter()
        # This should be good enough
        self.command_spam_cooldown = commands.CooldownMapping.from_cooldown(6, 5.0, commands.BucketType.user)

        self.prefixes = cache.LRUCache("prefixes", max_size=32)
        self.config = config.TOMLStorage('config.toml')
        self.version = version
        self._pending_cogs = {}

        headers = {"User-Agent": self.config['bot'].pop("user_agent", f"Lightning Bot {self.version}")}
        self.aiosession = aiohttp.ClientSession(headers=headers)
        self.redis_pool = cache.redis_pool

        path = pathlib.Path("lightning/cogs/")
        files = path.glob("**/*.py")
        cog_list = []
        for name in files:
            name = name.with_suffix("")
            cog_list.append(str(name).replace("/", "."))

        for cog in cog_list:
            if cog in self.config['bot']['disabled_cogs']:
                continue
            try:
                self.load_extension(cog)
            except Exception as e:
                log.error(f"Failed to load {cog}", exc_info=e)

        self.blacklisted_users = config.Storage("config/user_blacklist.json")

    async def create_pool(self, config: dict, **kwargs) -> None:
        """Creates a connection pool"""
        kwargs.update(config['tokens']['postgres'])

        async def init(connection: asyncpg.Connection):
            await connection.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
            await connection.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

        pool = await asyncpg.create_pool(init=init, **kwargs)
        self.pool = pool

    @cache.cached('guild_permissions', cache.Strategy.lru, max_size=32)
    async def get_permissions_config(self, guild_id):
        query = """SELECT * FROM guild_permissions WHERE guild_id=$1;"""
        record = await self.pool.fetchrow(query, guild_id)
        return GuildPermissions(record) if record else None

    @cache.cached("command_overrides", cache.Strategy.lru, max_size=32)
    async def get_command_overrides(self, guild_id: int) -> Optional[CommandOverrides]:
        query = """SELECT * FROM command_overrides WHERE guild_id=$1;"""
        record = await self.pool.fetch(query, guild_id)
        return CommandOverrides(record) if record else None

    def add_cog(self, cls) -> None:
        deps = getattr(cls, "__lightning_cog_deps__", None)
        if not deps:
            log.debug(f"Loaded cog {cls.__module__} ({cls})")
            super().add_cog(cls)
            return

        required_cogs = [self.get_cog(name) for name in deps.required]
        if not all(required_cogs):
            if hasattr(cls, '__name__'):
                self._pending_cogs[cls.__name__] = cls
            else:
                self._pending_cogs[cls.__class__.__name__] = cls
            return

        super().add_cog(cls)
        log.debug(f"Loaded LightningCog {cls.__module__} ({cls}).")

        # Try loading cogs pending
        pending_cogs = self._pending_cogs
        self._pending_cogs = {}
        for cog in list(pending_cogs.values()):
            log.debug(f"Trying to load {cog.__module__} ({str(cog)})")
            self.add_cog(cog)

    async def on_ready(self) -> None:
        summary = f"{len(self.guilds)} guild(s) and {len(self.users)} user(s)"
        log.info(f'READY: {str(self.user)} ({self.user.id}) and can see {summary}.')

    async def _notify_of_spam(self, member, channel, guild=None, blacklist=False) -> None:
        e = discord.Embed(color=discord.Color.red(), title="Member hit ratelimit")
        webhook = discord.Webhook.from_url(self.config['logging']['auto_blacklist'],
                                           adapter=discord.AsyncWebhookAdapter(self.aiosession))
        if blacklist:
            log.info(f"User automatically blacklisted for command spam | {member} | ID: {member.id}")
            e.title = "Automatic Blacklist"
        e.description = f"Spam Count: {self.command_spammers[member.id]}"
        donefmt = f'__Channel__: {channel} (ID: {channel.id})'
        if guild:
            donefmt = f'{donefmt}\n__Guild__: {guild} (ID: {guild.id})'
        e.add_field(name="Location", value=donefmt)
        e.add_field(name="User", value=f"{str(member)} (ID: {member.id})")
        e.timestamp = datetime.utcnow()
        await webhook.execute(embed=e)

    async def auto_blacklist_check(self, message) -> None:
        author = message.author.id
        if author in self.config['bot']['managers'] or author == self.owner_id:
            return

        bucket = self.command_spam_cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            # User hit the ratelimit
            self.command_spammers[author] += 1
            if self.command_spammers[author] >= self.config['bot']['spam_count']:
                await self.blacklisted_users.add(author, "Automatic blacklist on command spam")
                await self._notify_of_spam(message.author, message.channel, message.guild, True)
            # Notify ourselves that user is spamming
            else:
                await self._notify_of_spam(message.author, message.channel, message.guild)
                log.debug(f"User {message.author} ({author}) hit the command ratelimit")
        else:
            del self.command_spammers[author]

    async def process_command_usage(self, message):
        if str(message.author.id) in self.blacklisted_users:
            return

        ctx = await self.get_context(message, cls=LightningContext)
        if ctx.command is None:
            return

        await self.auto_blacklist_check(message)
        await self.invoke(ctx)

    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_command_usage(message)

    async def on_message_edit(self, before, after):
        if not self.config['bot']['edit_commands']:
            return

        if before.content != after.content:
            await self.on_message(after)

    async def on_command(self, ctx):
        log_text = f"{ctx.message.author} ({ctx.message.author.id}): "\
                   f"\"{ctx.message.content}\" "
        if ctx.guild:
            log_text += f"in \"{ctx.channel.name}\" ({ctx.channel.id}) "\
                        f"at \"{ctx.guild.name}\" ({ctx.guild.id})"
        else:
            log_text += f"in DMs ({ctx.channel.id})"
        log.info(log_text)

    async def on_error(self, event, *args, **kwargs):
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)
            log.exception(f"Error on {event}", exc_info=traceback.format_exc())

        with contextlib.suppress(discord.HTTPException):
            webhook = discord.Webhook.from_url(self.config['logging']['bot_errors'],
                                               adapter=discord.AsyncWebhookAdapter(self.aiosession))
            embed = discord.Embed(title="Event Error", description=f"```py\n{traceback.format_exc()}```",
                                  color=0xff0000,
                                  timestamp=datetime.utcnow())
            embed.add_field(name="Event", value=event)
            await webhook.execute(embed=embed, username="Event Error")

    async def log_command_error(self, ctx, error, *, send_error_message=True) -> str:
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

    async def on_command_error(self, ctx, error):
        # If command or cog has it's own error handler, return
        handler = getattr(ctx.cog, 'cog_command_error')
        overridden = ctx.cog._get_overridden_method(handler)
        if hasattr(ctx.command, 'on_error') or overridden:
            return

        error = getattr(error, "original", error)
        error_text = str(error)

        handled = ERROR_HANDLER_MESSAGES.get(type(error), None)
        if handled:
            await ctx.send(handled)
            return

        if isinstance(error, commands.BotMissingPermissions):
            p = ', '.join(error.missing_perms).replace('_', ' ').replace('guild', 'server').title()
            await ctx.send("I don't have the right permissions to run this command. "
                           f"I need: {p}")
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send("You are currently on cooldown. Try the command again in "
                           f"{error.retry_after:.1f} seconds.")
            return
        help_text = f"\nPlease see `{ctx.prefix}help {ctx.command}` for more info about this command."
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"You gave incorrect arguments. `{str(error)}` {help_text}")
            return
        elif isinstance(error, (commands.MissingRequiredArgument, errors.MissingRequiredFlagArgument)):
            codeblock = f"**{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}**\n\n{error_text}"
            await ctx.send(codeblock)
            return
        elif isinstance(error, commands.TooManyArguments):
            await ctx.send(f"You passed too many arguments.{help_text}")
            return
        elif isinstance(error, (errors.LightningError, errors.FlagError, menus.MenuError)):
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
            log.error(f"Uncaught error {type(error)}: {str(error)}")

        token = await self.log_command_error(ctx, error)

        # err_msg = f"An exception occurred with command \"{ctx.command.qualified_name}\""\
        #          f". See {token} for the traceback."
        # log.error(err_msg)

        embed = discord.Embed(title='Command Error', color=0xff0000,
                              timestamp=datetime.utcnow())
        embed.add_field(name='Name', value=ctx.command.qualified_name)
        embed.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        donefmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            donefmt = f'{donefmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'
        embed.add_field(name='Location', value=donefmt, inline=False)

        embed.add_field(name='Bug Token', value=token)
        adp = discord.AsyncWebhookAdapter(self.aiosession)
        webhook = discord.Webhook.from_url(self.config['logging']['bot_errors'], adapter=adp)
        await webhook.send(embed=embed)

    async def close(self) -> None:
        log.info("Shutting down...")
        log.info("Closing database...")
        await self.pool.close()
        await self.aiosession.close()
        log.info("Closed aiohttp session and database successfully.")
        if self.redis_pool:
            self.redis_pool.connection_pool.disconnect()
            log.info("Disconnected from Redis server")
        await super().close()
