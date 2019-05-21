import discord
from discord.ext import commands
from discord.ext.commands import Cog
import traceback
import inspect
import re
import os
from git import Repo
from subprocess import call
import time
import asyncio
from database import BlacklistGuild
import random
import config

# I should clean up this cog soon:tm:

class Owner(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_eval_result = None
        self.previous_eval_code = None
        self.repo = Repo(os.getcwd())
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.is_owner()
    @commands.command(hidden=True)
    async def fetchlog(self, ctx):
        """Returns log"""
        log_channel = self.bot.get_channel(config.error_channel)
        await ctx.message.add_reaction("✅")
        try:
            await ctx.author.send("Here's the current log file:", file=discord.File(f"{self.bot.script_name}.log"))
        except discord.errors.Forbidden:
            await ctx.send(f"💢 I couldn't send the log file in your DMs so I sent it to the bot's logging channel.")
            await log_channel.send("Here's the current log file:", file=discord.File(f"{self.bot.script_name}.log"))

    @commands.is_owner()
    @commands.command(name='blacklistguild')
    async def blacklist_guild(self, ctx, guild_id: int):
        """Blacklist a guild from using the bot"""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            msg = "**Note**: Lightning is not in that guild. This is a preventive blacklist.\n"
        else:
            msg = ""
            await guild.leave()

        session = self.bot.db.dbsession()
        blacklist = BlacklistGuild(guild_id=guild)
        session.merge(blacklist)
        session.commit()
        session.close()
        await ctx.send(msg + f'Successfully blacklisted {guild_id}')

    @commands.is_owner()
    @commands.command()
    async def restart(self, ctx):
        """Restart the bot"""
        await ctx.send('Restarting now...')
        time.sleep(1)
        await self.bot.logout()

    @commands.is_owner()
    @commands.command(hidden=True)
    async def leaveguild(self, ctx, server_id: int):
        """Leaves the guild via ID"""
        server = self.bot.get_guild(server_id)
        if server is None:
            return await ctx.send('I\'m not in this server.')
        await server.leave()
        await ctx.send(f'Successfully left {server.name}')
    
    @commands.is_owner() # Robocop-ng's eval commands. MIT Licensed. https://github.com/reswitched/robocop-ng/blob/master/LICENSE
    @commands.command(name='eval', hidden=True)
    async def _eval(self, ctx, *, code: str):
        """Evaluates some code, Owner only."""
        try:
            code = code.strip('` ')

            env = {
                'bot': self.bot,
                'ctx': ctx,
                'message': ctx.message,
                'server': ctx.guild,
                'guild': ctx.guild,
                'channel': ctx.message.channel,
                'author': ctx.message.author,

                # modules
                'discord': discord,
                'commands': commands,

                # utilities
                '_get': discord.utils.get,
                '_find': discord.utils.find,

                # last result
                '_': self.last_eval_result,
                '_p': self.previous_eval_code,
            }
            env.update(globals())

            self.bot.log.info(f"Evaling {repr(code)}:")
            result = eval(code, env)
            if inspect.isawaitable(result):
                result = await result

            if result is not None:
                self.last_eval_result = result

            self.previous_eval_code = code

            sliced_message = await self.bot.slice_message(repr(result),
                                                          prefix="```",
                                                          suffix="```")
            for msg in sliced_message:
                await ctx.send(msg)
        except:
            sliced_message = \
                await self.bot.slice_message(traceback.format_exc(),
                                             prefix="```",
                                             suffix="```")
            for msg in sliced_message:
                await ctx.send(msg)


    @commands.is_owner()
    @commands.group()
    async def git(self, ctx):
        """Git Commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.is_owner()
    @git.command(name='pull')
    @commands.guild_only()
    async def pull(self, ctx):
        """Pull new changes from GitHub."""
        msg = await ctx.send("<a:loading:568232137090793473> Pulling changes...")
        output = self.repo.git.pull()
        await msg.edit(content=f'📥 Pulled Changes:\n```diff\n{output}\n```')

    @commands.is_owner()
    @git.command(aliases=['pr'])
    @commands.guild_only()
    async def pullreload(self, ctx):
        """Pull and reload the cogs automatically."""
        msg = await ctx.send("<a:loading:568232137090793473> Pulling changes...")
        output = self.repo.git.pull()
        await msg.edit(content=f'📥 Pulled Changes:\n```diff\n{output}\n```')

        to_reload = re.findall(r'cogs/([a-z_]*).py[ ]*\|', output) # Read output

        for cog in to_reload: # Thanks Ave
                try:
                    self.bot.unload_extension("cogs." + cog)
                    self.bot.load_extension("cogs." + cog)
                    self.bot.log.info(f'Automatically reloaded {cog}')
                    await ctx.send(f'<:LightningCheck:571376826832650240> `{cog}` '
                                   'successfully reloaded.')
                except Exception as e:
                    await ctx.send(f'💢 There was an error reloading the cog \n**`ERROR:`** {type(e).__name__} - {e}')                   
                    return

    @commands.is_owner()
    @git.command(name="pull-load", aliases=['pl'])
    @commands.guild_only()
    async def pull_load(self, ctx):
        """Pull and load new cogs automatically."""
        msg = await ctx.send("<a:loading:568232137090793473> Pulling changes...")
        output = self.repo.git.pull()
        await msg.edit(content=f'📥 Pulled Changes:\n```diff\n{output}\n```')

        to_reload = re.findall(r'cogs/([a-z_]*).py[ ]*\|', output) # Read output

        for cog in to_reload: # Thanks Ave
                try:
                    self.bot.load_extension("cogs." + cog)
                    self.bot.log.info(f'Automatically loaded {cog}')
                    await ctx.send(f'<:LightningCheck:571376826832650240> `{cog}` '
                                   'successfully loaded.')
                except Exception as e:
                    await ctx.send(f'💢 There was an error loading the cog \n**`ERROR:`** {type(e).__name__} - {e}')                   
                    return

            
    @commands.command(name='playing', aliases=['status']) #'play'
    @commands.is_owner()
    async def playing(self, ctx, *gamename):
        """Sets playing message. Owner only."""
        await self.bot.change_presence(activity=discord.Game(name=f'{" ".join(gamename)}'))
        await ctx.send(f'Successfully changed status to `{gamename}`')

    @commands.command(name='stop', aliases=['bye', 'exit'])
    @commands.is_owner()
    async def stop(self, ctx):
        """Stop the Bot."""
        shutdown_messages = ['Shutting Down...', "See ya!", "RIP", "Turning off...."]
        await ctx.send(f"👋 {random.choice(shutdown_messages)}")
        time.sleep(20)
        await self.bot.close()

    @commands.command()
    @commands.is_owner()
    async def dm(self, ctx, user_id: discord.Member, *, message: str):
        """Direct messages a user""" # No checks yet
        await user_id.send(message)

    @commands.Cog.listener()
    async def on_guild_join(self, ctx, guild):
        session = self.bot.db.dbsession()
        guild_blacklist = session.query(BlacklistGuild).get(guild.id)
        if guild.id is guild_blacklist:
            await guild.leave()
            


def setup(bot):
    bot.add_cog(Owner(bot))
