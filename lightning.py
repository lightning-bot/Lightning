import yaml
import os
import sys
import discord
import logging
import logging.handlers
import traceback
from discord.ext import commands
from pathlib import Path
import aiohttp
import asyncio

import sys, traceback

config = yaml.safe_load(open('config.yml'))

# Uses template from ave's botbase.py
# botbase.py is under the MIT License. https://gitlab.com/ao/dpyBotBase/blob/master/LICENSE

script_name = os.path.basename(__file__).split('.')[0]

log_file_name = f"{script_name}.log"

# Limit of discord (non-nitro) is 8MB (not MiB)
max_file_size = 1000 * 1000 * 8
backup_count = 10000  # random big number
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

def get_prefix(bot, message):
    """A callable Prefix for our bot. This could be edited to allow per server prefixes."""

    prefixes = ['>', '.', '?']

    # Check to see if we are outside of a guild. e.g DM's etc.
    if not message.guild:
        # Only allow . to be used in DMs
        return '.'

    # If we are in a guild, we allow for the user to mention us or use any of the prefixes in our list.
    return commands.when_mentioned_or(*prefixes)(bot, message)


# Below cogs represents our folder our cogs are in. Following is the file name. So 'meme.py' in cogs, would be cogs.meme
initial_extensions = ['cogs.gifs',
                      'cogs.owner',
                      'cogs.load',
                      'cogs.mod',
                      'cogs.extras']

bot = commands.Bot(command_prefix=get_prefix, description='Small and simple version of Lightning. Lightning Lite')

bot.log = log
bot.config = config
bot.script_name = script_name

# Here we load our extensions(cogs) listed above in [initial_extensions].
if __name__ == '__main__':
    for extension in initial_extensions:
        try:
            bot.load_extension(extension)
        except Exception as e:
            print(f'Failed to load cog {extension}.')
            print(traceback.print_exc())


@bot.event
async def on_ready():
    aioh = {"User-Agent": f"{script_name}/1.0'"}
    bot.aiosession = aiohttp.ClientSession(headers=aioh)
    bot.app_info = await bot.application_info()

    log.info(f'\nLogged in as: {bot.user.name} - '
             f'{bot.user.id}\ndpy version: {discord.__version__}\n')
    game_name = f".help"
    await bot.change_presence(activity=discord.Game(name=game_name))

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

    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.send("This command doesn't work on DMs.")
    elif isinstance(error, commands.MissingPermissions):
        roles_needed = '\n- '.join(error.missing_perms)
        return await ctx.send(f"{ctx.author.mention}: You don't have the right"
                              " permissions to run this command. You need: "
                              f"```- {roles_needed}```")
    elif isinstance(error, commands.BotMissingPermissions):
        roles_needed = '\n-'.join(error.missing_perms)
        return await ctx.send(f"{ctx.author.mention}: Bot doesn't have "
                              "the right permissions to run this command. "
                              "Please add the following roles: "
                              f"```- {roles_needed}```")
    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"{ctx.author.mention}: You're being "
                              "ratelimited. Try in "
                              f"{error.retry_after:.1f} seconds.")
    elif isinstance(error, commands.CheckFailure):
        return await ctx.send(f"{ctx.author.mention}: Check failed. "
                              "You might not have the right permissions "
                              "to run this command.")

    help_text = f"Usage of this command is: ```{ctx.prefix}"\
                f"{ctx.command.signature}```\nPlease see `{ctx.prefix}help "\
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

@bot.command()
async def about(ctx):
    """About Lightning Lite"""
    embed = discord.Embed(title="Lightning Lite")
    embed.set_author(name="UmbraSage#7867")
    embed.set_thumbnail(url="https://assets.gitlab-static.net/uploads/-/system/user/avatar/3717366/avatar.png?width=90")
    embed.url = "https://gitlab.com/UmbraSage/bot.py"
    embed.description = "A small and simple bot. Designed for Lightning Hub server.\n\n Error Handling, credits to ave. <@426425345420296192>"
    await ctx.send(embed=embed)


bot.run(config["token"], bot=True, reconnect=True, loop=bot.loop)