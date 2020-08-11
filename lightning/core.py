# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
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
import asyncio
import collections
import contextlib
import io
import json
import logging
import pathlib
import platform
import secrets
import traceback
from datetime import datetime

import aiohttp
import aredis
import asyncpg
import discord
from discord.ext import commands, flags, menus

from lightning import cache, config
from lightning.meta import __version__ as version
from lightning.utils import errors, http
from lightning.utils.helpers import Emoji
from lightning.utils.menus import Confirmation

log = logging.getLogger(__name__)
ERROR_HANDLER_MESSAGES = {
    commands.NoPrivateMessage: "This command cannot be used in DMs!",
    commands.DisabledCommand: "Sorry, this command is currently disabled.",
    commands.NSFWChannelRequired: "This command can only be run in a NSFW marked channel or DMs."
}


async def _callable_prefix(bot, message):
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


LightningCogDeps = collections.namedtuple("LightningCogDeps", "required")


def lightningcog_d(required=None):
    def decorator(cls):
        setattr(cls, '__lightning_cog_deps__', LightningCogDeps(required=required or []))
        return cls
    return decorator


class LightningCog(commands.Cog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __init_subclass__(cls, *args, **kwargs):
        required_cogs = kwargs.get("required", [])
        cls.__lightning_cog_deps__ = LightningCogDeps(required=required_cogs)

    def __str__(self):
        """Returns the cog’s specified name, not the class name."""
        return self.qualified_name


class LightningContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def tick(self, boolean: bool):
        if boolean:
            tick = Emoji.greentick
        else:
            tick = Emoji.redtick
        await self.send(tick)

    async def safe_send(self, content=None, *, use_file=False, **kwargs):
        return await self.send(content, **kwargs)

    async def emoji_send(self, emoji):
        """Attempts to send the specified emote. If failed, reacts."""
        try:
            await self.message.channel.send(emoji)
        except discord.Forbidden:
            await self.message.add_reaction(emoji)

    async def prompt(self, message, *, delete_after=False, confirmation_message=True):
        resp = await Confirmation(self, message, delete_message_after=delete_after,
                                  confirmation_message=confirmation_message).prompt()
        return resp

    async def send(self, content=None, *args, **kwargs):
        if content:
            if len(content) > 2000:
                try:
                    mysturl = await http.haste(self.bot.aiosession, content)
                    content = f"Content too long: {mysturl}"
                except errors.LightningError:
                    fp = io.StringIO(content)
                    content = "Content too long..."
                    return await super().send(content, file=discord.File(fp, filename='message_too_long.txt'))
        return await super().send(content, *args, **kwargs)


class LightningBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(command_prefix=_callable_prefix, reconnect=True,
                         allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False))
        self.launch_time = datetime.utcnow()

        self.command_spammers = collections.Counter()
        # This should be good enough
        self.command_spam_cooldown = commands.CooldownMapping.from_cooldown(6, 5.0, commands.BucketType.user)

        self.prefixes = cache.Cache(cache.Strategy.lru)
        self.config = config.TOMLStorage('config.toml')
        self.version = version
        self._pending_cogs = {}

        headers = {"User-Agent": self.config['bot'].pop("user_agent", f"Lightning Bot {self.version}")}
        self.aiosession = aiohttp.ClientSession(headers=headers)

        try:
            self.redis_pool = aredis.StrictRedis()
            # Only way to ensure a redis server is setup
            self.loop.run_until_complete(self.redis_pool.ping())
        except Exception as e:
            log.warning(f"Redis caching is disabled! {e}")
            self.redis_pool = None

        path = pathlib.Path("lightning/cogs/")
        files = path.glob('**/*.py')
        cog_list = []
        for name in files:
            name = name.with_suffix("")
            cog_list.append(str(name).replace("/", "."))

        for cog in cog_list:
            try:
                self.load_extension(cog)
            except Exception:
                log.error(f'Failed to load {cog}')
                traceback.print_exc()

        self.blacklisted_users = config.Storage("config/user_blacklist.json")
        if self.config['bot']['whitelist']:
            log.warning("Whitelist system is toggled on! Make sure to whitelist servers you want to use the bot!")
            self.guild_whitelist = config.Storage("config/whitelist.json")

    async def create_pool(self, config: dict, **kwargs) -> None:
        """Creates a connection pool"""
        kwargs.update(config['tokens']['postgres'])

        async def init(connection: asyncpg.Connection):
            await connection.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
            await connection.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

        pool = await asyncpg.create_pool(init=init, **kwargs)
        self.pool = pool

    def add_cog(self, cls):
        deps = getattr(cls, "__lightning_cog_deps__", None)
        if not deps:
            log.warn(f"{cls.__module__} ({cls.__class__.__name__}) should use LightningCog.")
            return super().add_cog(cls)

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
        log.info(f'\nLogged in as: {self.user.name} - '
                 f'{self.user.id}\ndpy version: '
                 f'{discord.__version__}\nVersion: {self.version}\n')

        summary = f"{len(self.guilds)} guild(s) and {len(self.users)} user(s)"
        msg = f"{self.user.name} has started! "\
              f"I can see {summary}\n\ndiscord.py Version: "\
              f"{discord.__version__}"\
              f"\nRunning on Python {platform.python_version()}"\
              f"\nI'm currently on **{self.version}**"
        with contextlib.suppress(Exception):
            channel = self.get_channel(self.config['logging']['startup'])
            await channel.send(msg, delete_after=250)

    async def _notify_spam(self, member, channel, guild=None, blacklist=False) -> None:
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
                await self._notify_spam(message.author, message.channel, message.guild, True)
            # Notify ourselves that user is spamming
            else:
                await self._notify_spam(message.author, message.channel, message.guild)
                log.debug(f"User {message.author} ({author}) hit the command ratelimit")
        else:
            del self.command_spammers[author]

    async def process_command_usage(self, message):
        if str(message.author.id) in self.blacklisted_users:
            return

        if message.guild:
            if hasattr(self, 'guild_whitelist'):
                if str(message.guild.id) not in self.guild_whitelist:
                    await message.guild.leave()
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

    async def on_error(self, event_method, *args, **kwargs):
        log.error(f"Error on {event_method}: {traceback.format_exc()}")
        with contextlib.suppress(discord.HTTPException):
            webhook = discord.Webhook.from_url(self.config['logging']['bot_errors'],
                                               adapter=discord.AsyncWebhookAdapter(self.aiosession))
            embed = discord.Embed(title="Event Error", description=f"```py\n{traceback.format_exc()}```",
                                  color=0xff0000,
                                  timestamp=datetime.utcnow())
            embed.add_field(name="Event", value=event_method)
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
        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await ctx.send(f"\N{BUG} An unexpected error occurred. `{token}`")
        return token

    async def on_command_error(self, ctx, error):
        error_text = str(error)
        # If command or cog has it's own error handler, return
        handler = getattr(ctx.cog, 'cog_command_error')
        overridden = ctx.cog._get_overridden_method(handler)
        if hasattr(ctx.command, 'on_error') or overridden:
            return

        handled = ERROR_HANDLER_MESSAGES.get(type(error), None)
        if handled:
            return await ctx.send(handled)

        if isinstance(error, commands.MissingPermissions):
            p = ', '.join(error.missing_perms).replace('_', ' ').replace('guild', 'server').title()
            return await ctx.send(f"{ctx.author.mention}: You don't have the right"
                                  f" permissions to run this command. You need: {p}",
                                  allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        elif isinstance(error, commands.BotMissingPermissions):
            p = ', '.join(error.missing_perms).replace('_', ' ').replace('guild', 'server').title()
            return await ctx.send("I don't have the right permissions to run this command. "
                                  f"I need: {p}")
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send("You are currently on cooldown. Try the command again in "
                                  f"{error.retry_after:.1f} seconds.")
        help_text = f"\nPlease see `{ctx.prefix}help {ctx.command}` for more info about this command."
        if isinstance(error, commands.BadArgument):
            return await ctx.send(f"You gave incorrect arguments. `{str(error)}` {help_text}")
        elif isinstance(error, commands.MissingRequiredArgument):
            codeblock = f"**{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}**\n\n{error_text}"
            return await ctx.send(codeblock)
        elif isinstance(error, commands.TooManyArguments):
            return await ctx.send(f"You passed too many arguments.{help_text}")
        elif isinstance(error, (errors.LightningError, flags.ArgumentParsingError)):
            return await ctx.send(error_text)

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, asyncio.TimeoutError):
                return await ctx.send(f'{ctx.command.qualified_name} timed out.')
            elif isinstance(error.original, menus.MenuError):
                return await ctx.send(str(error.original))
        log.error(f"Uncaught error {type(error.original)}: {str(error.original)}")

        # Errors that should give no output.
        if isinstance(error, (commands.NotOwner, commands.CommandNotFound,
                              commands.CheckFailure)):
            return

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

    async def close(self):
        log.info("Shutting down...")
        log.info("Closing database...")
        await self.pool.close()
        await self.aiosession.close()
        log.info("Closed aiohttp session and database successfully.")
        if self.redis_pool:
            self.redis_pool.connection_pool.disconnect()
            log.info("Disconnected from Redis server")
        await super().close()
