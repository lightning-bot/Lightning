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
import db.per_guild_config
import config
from dhooks import Embed, Webhook


# Uses template from ave's botbase.py
# botbase.py is under the MIT License. https://gitlab.com/ao/dpyBotBase/blob/master/LICENSE

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

default_prefix = '.', 'l.'

def _callable_prefix(bot, message):
    prefixes = default_prefix
    return commands.when_mentioned_or(*prefixes)(bot, message)


initial_extensions = config.cogs

bot = commands.Bot(command_prefix=_callable_prefix, description=config.description)
bot.launch_time = datetime.utcnow()

bot.log = log
bot.config = config
bot.help_command = commands.DefaultHelpCommand(dm_help = None)
bot.script_name = script_name
failed_to_load_cogs = []
success_cogs = []

# Here we load our extensions(cogs) listed above in [initial_extensions].
if __name__ == '__main__':
    for extension in initial_extensions:
        try:
            bot.load_extension(extension)
            success_cogs.append([extension])
        except Exception as e:
            log.error(f'Failed to load cog {extension}.')
            log.error(traceback.print_exc())
            failed_to_load_cogs.append([extension, type(e).__name__, e])

def load_jis():
    bot.load_extension('jishaku')
    log.info("Jishaku loaded")

load_jis()

version_num = "v1.1.10"
bot.version = version_num

@bot.event
async def on_ready():
    aioh = {"User-Agent": f"{script_name}/1.0'"}
    bot.aiosession = aiohttp.ClientSession(headers=aioh)
    bot.app_info = await bot.application_info()
    bot.botlog_channel = bot.get_channel(config.error_channel)

    log.info(f'\nLogged in as: {bot.user.name} - '
             f'{bot.user.id}\ndpy version: {discord.__version__}\nVersion: {bot.version}\n')
    summary = f"{len(bot.guilds)} guild(s) and {len(bot.users)} user(s)"
    msg = f"{bot.user.name} has started! "\
          f"I can see {summary}\n\nDiscord.py Version: {discord.__version__}"\
          f"\nRunning on Python {platform.python_version()}"\
          f"\nI'm currently on **{bot.version}**"
    if len(success_cogs) != 0:
        info = "Cog Info:\n\n"
        info += "Loaded Cogs:\n"
        for s in success_cogs:
            info += "{}\n".format(*s)
        if len(failed_to_load_cogs) != 0:
            for b in failed_to_load_cogs:
                info += "Failed to load {}: `{}: {}`\n".format(*b)
        url = await bot.haste(info) # Common Cog needs to be loaded so it can generate the haste
        msg += f"\n__Information about cogs loaded and failed__ -> {url}"

    await bot.botlog_channel.send(msg)

@bot.event
async def on_command(ctx):
    log_text = f"{ctx.message.author} ({ctx.message.author.id}): "\
               f"\"{ctx.message.content}\" "
    if ctx.guild:  # was too long for tertiary if
        log_text += f"on \"{ctx.channel.name}\" ({ctx.channel.id}) "\
                    f"at \"{ctx.guild.name}\" ({ctx.guild.id})"
    else:
        log_text += f"on DMs ({ctx.channel.id})"
    log.info(log_text)


@bot.event
async def on_error(event_method, *args, **kwargs):
    log.error(f"Error on {event_method}: {sys.exc_info()}")


# Error handling thanks to Ave's botbase.py and Robocop from Reswitched.
# botbase.py is under the MIT License. https://gitlab.com/ao/dpyBotBase/blob/master/LICENSE
# https://gitlab.com/ao/dpyBotBase and Robocop-ng is under the MIT License too. https://github.com/reswitched/robocop-ng

@bot.event
async def on_command_error(ctx, error):
    error_text = str(error)

    err_msg = f"Error with \"{ctx.message.content}\" from "\
              f"\"{ctx.message.author} ({ctx.message.author.id}) "\
              f"of type {type(error)}: {error_text}"
    log.error(err_msg)

    hook = Webhook(config.webhookurl) # Log Errors
    embed = Embed(description=f"{err_msg}", color=0xff0000, timestamp='now')
    embed.set_title(title="ERROR")
    hook.send(embed=embed)

    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.send("This command doesn't work in DMs.")
    elif isinstance(error, commands.MissingPermissions):
        roles_needed = '\n- '.join(error.missing_perms)
        return await ctx.send(f"{ctx.author.mention}: You don't have the right"
                              " permissions to run this command. You need: "
                              f"```- {roles_needed}```")
    elif isinstance(error, commands.BotMissingPermissions):
        roles_needed = '\n-'.join(error.missing_perms)
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
                              "You might not have the right permissions "
                              "to run this command.")
    elif isinstance(error, discord.NotFound):
        return await ctx.send("❌ I wasn't able to find that ID.")

    help_text = f"Usage of this command is: ```{ctx.prefix}"\
                f"{ctx.invoked_with} {ctx.command.signature}```\nPlease see `{ctx.prefix}help "\
                f"{ctx.command.name}` for more info about this command."
    if isinstance(error, commands.BadArgument):
        return await ctx.send(f"{ctx.author.mention}: You gave incorrect "
                              f"arguments. {help_text}")
    elif isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(f"{ctx.author.mention}: You gave incomplete "
                              f"arguments. {help_text}")
    elif isinstance(error, commands.CommandInvokeError) and\
            ("Cannot send messages to this user" in error_text):
        return await ctx.send(f"{ctx.author.mention}: I can't DM you.\n"
                              "You might have me blocked or have DMs "
                              f"blocked globally or for {ctx.guild.name}.\n"
                              "Please resolve that, then "
                              "run the command again.")
    elif isinstance(error, commands.CommandNotFound):
        return

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    await bot.invoke(ctx)



bot.run(config.token, bot=True, reconnect=True, loop=bot.loop)
