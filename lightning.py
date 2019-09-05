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

import os
import sys
import discord
import platform
import logging
import logging.handlers
import traceback
from discord.ext import commands
import aiohttp
from datetime import datetime
import config
import db.per_guild_config
import asyncpg
import asyncio

# Uses logging template from ave's botbase.py
# botbase.py is under the MIT License. 
# https://gitlab.com/ao/dpyBotBase/blob/master/LICENSE

script_name = os.path.basename(__file__).split('.')[0]

log_file_name = f"{script_name}.log"

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

default_prefix = config.default_prefix

def _callable_prefix(bot, message):
    prefixed = default_prefix
    if message.guild is None:
        return commands.when_mentioned_or(*prefixed)(bot, message)
    if db.per_guild_config.exist_guild_config(message.guild, "prefixes"):
        guild_config = db.per_guild_config.get_guild_config(message.guild, "prefixes")
    else:
        return commands.when_mentioned_or(*prefixed)(bot, message)
    if "prefixes" in guild_config:
        prefixesc = guild_config["prefixes"]
        prefixesc += default_prefix
        return commands.when_mentioned_or(*prefixesc)(bot, message)

initial_extensions = config.cogs

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

class LightningBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=_callable_prefix, 
                         description=config.description)
        self.version = "v2.0A"
        self.log = log
        self.launch_time = datetime.utcnow()
        self.script_name = script_name
        self.success_cogs = []
        self.unloaded_cogs = []
        self.successful_command = 0
        self.command_spammers = {}

        for ext in initial_extensions:
            try:
                self.load_extension(ext)
                self.success_cogs.append(ext)
            except Exception:
                log.error(f'Failed to load cog {ext}.')
                log.error(traceback.print_exc())
                self.unloaded_cogs.append(ext)
        try:
            self.load_extension('jishaku')
            self.success_cogs.append('jishaku')
        except Exception:
            log.error(f"Failed to load jishaku.")
            log.error(traceback.print_exc())
            self.unloaded_cogs.append("jishaku")

    async def create_pool(self, dbs, **kwargs):
        """Creates a connection pool"""
        # Mainly prevent multiple pools
        pool = await asyncpg.create_pool(dbs, **kwargs)
        return pool

    async def auto_append_cogs(self):
        """Automatically append all extra cogs not loaded
            as unloaded"""
        for ext in os.listdir("cogs"):
            external = f"cogs.{ext[:-3]}"
            if ext.endswith(".py") and external not in self.success_cogs:
                self.unloaded_cogs.append(f"cogs.{ext[:-3]}")

    async def on_ready(self):
        aioh = {"User-Agent": f"{script_name}/1.0'"}
        self.aiosession = aiohttp.ClientSession(headers=aioh)
        self.app_info = await self.application_info()
        self.botlog_channel = self.get_channel(config.error_channel)

        log.info(f'\nLogged in as: {self.user.name} - '
                f'{self.user.id}\ndpy version: '
                f'{discord.__version__}\nVersion: {self.version}\n')
        summary = f"{len(self.guilds)} guild(s) and {len(self.users)} user(s)"
        msg = f"{self.user.name} has started! "\
              f"I can see {summary}\n\nDiscord.py Version: "\
              f"{discord.__version__}"\
              f"\nRunning on Python {platform.python_version()}"\
              f"\nI'm currently on **{self.version}**"
        await self.botlog_channel.send(msg, delete_after=250)

    async def auto_blacklist_check(self, message):
        if message.author.id in config.bot_managers:
            return
        try:
            self.command_spammers[str(message.author.id)] += 1
        except KeyError:
            self.command_spammers[str(message.author.id)] = 1
        if self.command_spammers[str(message.author.id)] >= config.spam_count:
            bl = self.get_cog('Owner')
            if not bl:
                self.log.error("Owner Cog Is Not Loaded.")
            if bl:
                # If owner cog is loaded, grab blacklist and blacklist the user
                # who is spamming and notify us of the person who just got
                # blacklisted for spamming.
                td = bl.grab_blacklist()
                if str(message.author.id) in td:
                    return
                td[str(message.author.id)] = "Automatic blacklist on command spam"
                bl.blacklist_dump("user_blacklist", td)
                embed = discord.Embed(title="🚨 Auto User Blacklist", 
                                      color=discord.Color.red())
                embed.description=f"User: {message.author}\n"\
                                  f"Spammed Commands "\
                                  f"Count: {self.command_spammers[str(message.author.id)]}"
                wbhk = discord.Webhook.from_url
                adp = discord.AsyncWebhookAdapter(self.aiosession)
                webhook = wbhk(config.webhook_blacklist_alert, adapter=adp)
                self.log.info(f"User automatically blacklisted for command spam |"
                              f" {message.author} | ID: {message.author.id}")
                await webhook.execute(embed=embed)

    async def process_command_usage(self, message):
        await self.auto_blacklist_check(message)
        bl = self.get_cog('Owner')
        if not bl:
            self.log.error("Owner Cog Is Not Loaded.")
        if bl:
            if str(message.author.id) in bl.grab_blacklist():
                return
            if str(message.guild.id) in bl.grab_blacklist_guild():
                return
        ctx = await self.get_context(message, cls=LightningContext)
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
                webhook = webhook(config.webhookurl, adapter=adp)
                embed = discord.Embed(title="⚠ Error",
                                      description=err_msg,
                                      color=discord.Color(0xff0000),
                                      timestamp=datetime.utcnow())
                await webhook.execute(embed=embed)
            except:
                pass

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("This command doesn't work in DMs.")
        elif isinstance(error, commands.MissingPermissions):
            roles_needed = '\n- '.join(error.missing_perms)
            return await ctx.send(f"{ctx.author.mention}: You don't have the right"
                                  " permissions to run this command. You need: "
                                  f"```- {roles_needed}```")
        elif isinstance(error, commands.BotMissingPermissions):
            roles_needed = '\n -'.join(error.missing_perms)
            return await ctx.send(f"{ctx.author.mention}: Bot doesn't have "
                                  "the right permissions to run this command. "
                                  "Please add the following permissions: "
                                  f"```- {roles_needed}```")
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"{ctx.author.mention}: ⚠ You're being "
                                  "ratelimited. Try again in "
                                  f"{error.retry_after:.1f} seconds.")
        elif isinstance(error, commands.NotOwner):
            return await ctx.send(f"{ctx.author.mention}: ❌ You cannot use this command "
                                  "as it's only for the owner of the bot!")
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
            return # We don't need to say anything