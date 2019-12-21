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
import logging
import logging.handlers
import os
import platform
import sys
import traceback
from datetime import datetime

import aiohttp
import asyncpg
import discord
import toml
from discord.ext import commands

from utils import errors
from resources import botemojis

log_file_name = "lightning.log"

# Limit of discord (non-nitro) is 8MB (not MiB)
max_file_size = 1000 * 1000 * 8
backup_count = 10
file_handler = logging.handlers.RotatingFileHandler(
    filename=log_file_name, maxBytes=max_file_size, backupCount=backup_count)
stdout_handler = logging.StreamHandler(sys.stdout)
log_format = logging.Formatter(
    '[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
stdout_handler.setFormatter(log_format)

log = logging.getLogger('discord')
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(stdout_handler)
# logging.getLogger('discord.http').setLevel(logging.WARNING)
# Remove spammy log messages
logging.getLogger('discord.state').addFilter(lambda l: 'Processed a chunk' not in l.msg)


async def _callable_prefix(bot, message):
    prefixed = ['l+']
    if message.guild is None:
        return commands.when_mentioned_or(*prefixed)(bot, message)
    if message.guild.id in bot.prefixes:
        prefixes = bot.prefixes[message.guild.id]
        return commands.when_mentioned_or(*prefixes)(bot, message)
    else:
        ret = await bot.db.fetchval("SELECT prefix FROM guild_config WHERE guild_id=$1",
                                    message.guild.id)
        if ret:
            bot.prefixes[message.guild.id] = ret
            return commands.when_mentioned_or(*ret)(bot, message)
        else:
            return commands.when_mentioned(bot, message)


initial_extensions = ['cogs.config',
                      'cogs.emoji',
                      'cogs.fun',
                      'cogs.git',
                      'cogs.lightning-hub',
                      'cogs.memes',
                      'cogs.meta',
                      'cogs.mod',
                      'cogs.owner',
                      'cogs.tasks',
                      'cogs.timers',
                      'cogs.toggle_roles',
                      'cogs.utility',
                      'stabilite.stabilite',
                      'cogs.misc',
                      'bolt']

# Create config folder if not found
if not os.path.exists("config"):
    os.makedirs("config")
if not os.path.exists("cogs"):
    os.makedirs("cogs")


class LightningContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def safe_send(self, content=None, **kwargs):
        # I hope this saves my life forever. :blobsweat:
        if content is not None:
            content = await commands.clean_content().convert(self, str(content))
        return await super().send(content=content, **kwargs)

    async def emoji_send(self, emoji):
        """Attempts to send the specified emote. If failed, reacts."""
        try:
            await self.message.channel.send(emoji)
        except discord.Forbidden:
            await self.message.add_reaction(emoji)
    # R.Danny based ctx.prompt.
    # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/context.py#L86

    async def prompt(self, message, *, timeout=60.0, delete_after=True, author_id=None):
        """An interactive reaction confirmation dialog.
        Parameters
        -----------
        message: str
            The message to show along with the prompt.
        timeout: float
            How long to wait before returning.
        delete_after: bool
            Whether to delete the confirmation message after we're done.
        author_id: Optional[int]
            The member who should respond to the prompt. Defaults to the author of the
            Context's message.
        Returns
        --------
        Optional[bool]
            ``True`` if explicit confirm,
            ``False`` if explicit deny,
            ``None`` if deny due to timeout
        """

        if not self.channel.permissions_for(self.me).add_reactions:
            raise errors.LightningError('Bot does not have Add Reactions permission.')

        fmt = f'{message}\n\nReact with \N{WHITE HEAVY CHECK MARK} to confirm or \N{CROSS MARK} to deny.'

        author_id = author_id or self.author.id
        msg = await self.send(fmt)

        confirm = None

        def check(payload):
            nonlocal confirm

            if payload.message_id != msg.id or payload.user_id != author_id:
                return False

            codepoint = str(payload.emoji)

            if codepoint == '\N{WHITE HEAVY CHECK MARK}':
                confirm = True
                return True
            elif codepoint == '\N{CROSS MARK}':
                confirm = False
                return True

            return False

        for emoji in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'):
            await msg.add_reaction(emoji)

        try:
            await self.bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            confirm = None

        try:
            if delete_after:
                await msg.delete()
        finally:
            return confirm


class LightningBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(command_prefix=_callable_prefix)
        self.log = log
        self.launch_time = datetime.utcnow()
        self.script_name = "lightning"
        self.successful_command = 0
        self.command_spammers = {}
        # Initialize as none then cache our prefixes on_ready
        self.prefixes = {}
        self.config = toml.load('config.toml')

        for ext in initial_extensions:
            try:
                self.load_extension(ext)
            except Exception:
                log.error(f'Failed to load {ext}.')
                log.error(traceback.print_exc())
        try:
            self.load_extension('jishaku')
        except Exception:
            log.error("Failed to load jishaku.")
            log.error(traceback.print_exc())

        bl = self.get_cog('Owner')
        if not bl:
            self.log.error("Owner Cog Is Not Loaded.")
        if bl:
            self.blacklisted_users = bl.grab_blacklist()
            self.blacklisted_guilds = bl.grab_blacklist_guild()

    async def create_pool(self, dbs, **kwargs):
        """Creates a connection pool and initializes our prefixes"""
        # Mainly prevent multiple pools
        pool = await asyncpg.create_pool(dbs, **kwargs)
        return pool

    async def on_ready(self):
        aioh = {"User-Agent": f"Lightning/{self.config['bot']['version']}'"}
        self.aiosession = aiohttp.ClientSession(headers=aioh)
        self.app_info = await self.application_info()
        self.botlog_channel = self.get_channel(self.config['logging']['startup'])

        log.info(f'\nLogged in as: {self.user.name} - '
                 f'{self.user.id}\ndpy version: '
                 f'{discord.__version__}\nVersion: {self.config["bot"]["version"]}\n')
        summary = f"{len(self.guilds)} guild(s) and {len(self.users)} user(s)"
        msg = f"{self.user.name} has started! "\
              f"I can see {summary}\n\nDiscord.py Version: "\
              f"{discord.__version__}"\
              f"\nRunning on Python {platform.python_version()}"\
              f"\nI'm currently on **{self.config['bot']['version']}**"
        await self.botlog_channel.send(msg, delete_after=250)
        if self.config['bot']['game']:
            init_game = discord.Game(self.config['bot']['game'])
            await self.change_presence(activity=init_game)

    async def auto_blacklist_check(self, message):
        if message.author.id in self.config['bot']['managers']:
            return
        try:
            self.command_spammers[str(message.author.id)] += 1
        except KeyError:
            self.command_spammers[str(message.author.id)] = 1
        if self.command_spammers[str(message.author.id)] >= self.config['bot']['spam_count']:
            bl = self.get_cog('Owner')
            if not bl:
                self.log.error("Owner Cog Is Not Loaded.")
            if bl:
                # If owner cog is loaded, grab blacklist and blacklist the user
                # who is spamming and notify us of the person who just got
                # blacklisted for spamming.
                td = self.blacklisted_users
                if str(message.author.id) in td:
                    return
                td[str(message.author.id)] = "Automatic blacklist on command spam"
                bl.blacklist_dump("user_blacklist", td)
                embed = discord.Embed(title="🚨 Auto User Blacklist",
                                      color=discord.Color.red())
                embed.description = f"User: {message.author}\n"\
                                    f"Spammed Commands "\
                                    f"Count: "\
                                    f"{self.command_spammers[str(message.author.id)]}"
                wbhk = discord.Webhook.from_url
                adp = discord.AsyncWebhookAdapter(self.aiosession)
                webhook = wbhk(self.config['logging']['auto_blacklist'], adapter=adp)
                self.log.info(f"User automatically blacklisted for command spam |"
                              f" {message.author} | ID: {message.author.id}")
                await webhook.execute(embed=embed)

    async def process_command_usage(self, message):
        if f"{message.author.id}" in self.blacklisted_users:
            return
        if message.guild:
            if f"{message.guild.id}" in self.blacklisted_guilds:
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

    async def on_command(self, ctx):
        log_text = f"{ctx.message.author} ({ctx.message.author.id}): "\
                   f"\"{ctx.message.content}\" "
        if ctx.guild:  # was too long for tertiary if
            log_text += f"on \"{ctx.channel.name}\" ({ctx.channel.id}) "\
                        f"at \"{ctx.guild.name}\" ({ctx.guild.id})"
        else:
            log_text += f"on DMs ({ctx.channel.id})"
        log.info(log_text)

    # Error Handling mostly based on Robocop-NG (MIT Licensed)
    # https://github.com/reswitched/robocop-ng/blob/master/Robocop.py
    async def on_error(self, event_method, *args, **kwargs):
        log.error(f"Error on {event_method}: {sys.exc_info()}")
        await self.wait_until_ready()
        webhook = discord.Webhook.from_url
        adp = discord.AsyncWebhookAdapter(self.aiosession)
        try:
            webhook = webhook(self.config['logging']['bot_errors'], adapter=adp)
            embed = discord.Embed(title=f"⚠ Error on {event_method}",
                                  description=f"{sys.exc_info()}",
                                  color=discord.Color(0xff0000),
                                  timestamp=datetime.utcnow())
            await webhook.execute(embed=embed, username=f"{str(event_method)}")
        except Exception:
            return

    async def on_command_error(self, ctx, error):
        error_text = str(error)

        err_msg = f"Error with \"{ctx.message.content}\" from "\
                  f"\"{ctx.message.author} ({ctx.message.author.id}) "\
                  f"of type {type(error)}: {error_text}"
        log.error(err_msg)

        if not isinstance(error, commands.CommandNotFound):
            webhook = discord.Webhook.from_url
            adp = discord.AsyncWebhookAdapter(self.aiosession)
            try:
                webhook = webhook(self.config['logging']['bot_errors'], adapter=adp)
                embed = discord.Embed(title="⚠ Error",
                                      description=err_msg,
                                      color=discord.Color(0xff0000),
                                      timestamp=datetime.utcnow())
                await webhook.execute(embed=embed)
            except Exception:
                pass

        if hasattr(ctx.command, 'on_error'):
            return

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("This command doesn't work in DMs.")
        elif isinstance(error, commands.MissingPermissions):
            roles_needed = '\n- '.join(error.missing_perms)
            return await ctx.send(f"{ctx.author.mention}: You don't have the right"
                                  " permissions to run this command. You need: "
                                  f"```- {roles_needed}```")
        elif isinstance(error, commands.BotMissingPermissions):
            roles_needed = '\n- '.join(error.missing_perms)
            return await ctx.send(f"{ctx.author.mention}: I don't have "
                                  "the right permissions to run this command. "
                                  "Please add the following permissions to me: "
                                  f"```- {roles_needed}```")
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send("⚠ You're being "
                                  "ratelimited. Try again in "
                                  f"{error.retry_after:.1f} seconds.")
        elif isinstance(error, commands.NotOwner):
            try:
                return await ctx.message.add_reaction(botemojis.x)
            except discord.HTTPException:
                return
        elif isinstance(error, commands.NSFWChannelRequired):
            return await ctx.send(f"{ctx.author.mention}: This command "
                                  "can only be run in a NSFW marked channel or DMs.")
        elif isinstance(error, commands.CheckFailure):
            return await ctx.send(f"{ctx.author.mention}: Check failed. "
                                  "You do not have the right permissions "
                                  "to run this command.")
        elif isinstance(error, discord.NotFound):
            return await ctx.send("❌ I wasn't able to find that ID.")
        elif isinstance(error, commands.DisabledCommand):
            return await ctx.send(f"{ctx.author.mention}: This command is currently "
                                  "disabled!")
        help_text = f"\n\nPlease see `{ctx.prefix}help "\
                    f"{ctx.command}` for more info about this command."
        if isinstance(error, commands.BadArgument):
            content = await commands.clean_content().convert(ctx, str(error))
            return await ctx.send(f"{ctx.author.mention}: You gave incorrect "
                                  f"arguments. `{content}` {help_text}")
        elif isinstance(error, commands.MissingRequiredArgument):
            content = await commands.clean_content().convert(ctx, str(error))
            return await ctx.send(f"{ctx.author.mention}: You gave incomplete "
                                  f"arguments. `{content}` {help_text}")
        elif isinstance(error, commands.CommandInvokeError) and\
                ("Cannot send messages to this user" in error_text):
            return await ctx.send(f"{ctx.author.mention}: I can't DM you.\n"
                                  "You might have me blocked or have DMs "
                                  f"blocked globally or for {ctx.guild.name}.\n"
                                  "Please resolve that, then "
                                  "run the command again.")
        elif isinstance(error, commands.CommandNotFound):
            return  # We don't need to say anything
        elif isinstance(error, errors.NoWarns):
            return await ctx.send(error_text)
        elif isinstance(error, errors.LightningError):
            return await ctx.safe_send(error_text)
        err = self.get_cog('Meta')
        if err:
            await err.create_error_ticket(ctx, "Command Error", f"{error}")
