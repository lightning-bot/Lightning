import discord
from discord.ext import commands
from discord.ext.commands import Cog
import traceback
import inspect
import re
import os
from git import Repo
import time
from database import BlacklistGuild, BlacklistUser
from utils.restrictions import add_restriction
import random
import config
import asyncio
import subprocess


class Owner(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_eval_result = None
        self.previous_eval_code = None
        self.repo = Repo(os.getcwd())
        self.bot.log.info(f'{self.qualified_name} loaded')
        
    @commands.is_owner()
    @commands.command()
    async def shell(self, ctx, *, command: str):
        """Runs a command in the terminal/shell"""
        try:
            pipe = asyncio.subprocess.PIPE
            process = await asyncio.create_subprocess_shell(command,
                                                            stdout=pipe,
                                                            stderr=pipe)
            stdout, stderr = await process.communicate()
        except NotImplementedError: # Account for Windows (Trashdows)
            process = subprocess.Popen(command, shell=True, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE)
            stdout, stderr = await process.communicate()
            
        msg1 = f"[stderr]\n{stderr.decode('utf-8')}\n---\n"\
               f"[stdout]\n{stdout.decode('utf-8')}"
        sliced_message = await self.bot.slice_message(msg1,
                                                      prefix="```",
                                                      suffix="```")
        for msg in sliced_message:
            await ctx.send(msg)
    
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
    
    @commands.command(name="fetchguilduserlog")
    @commands.guild_only()
    @commands.is_owner()
    async def getmodlogjson(self, ctx, guild_id: int):
        """Gets the guild id's userlog.json file"""
        try:
            await ctx.send(f"Here's the userlog.json for `{guild_id}`", file=discord.File(f"config/{guild_id}/userlog.json"))
        except:
            await ctx.send(f"`{guild_id}` doesn't have a userlog.json yet. Check back later.")

    @commands.is_owner()
    @commands.command(name='blacklistguild')
    async def blacklist_guild(self, ctx, server_id: int):
        """Blacklist a guild from using the bot"""
        guild = self.bot.get_guild(server_id)
        if guild is None:
            msg = "**Note**: Lightning is not in that guild. This is a preventive blacklist.\n"
        else:
            msg = ""
            await guild.leave()

        session = self.bot.db.dbsession()
        blacklist = BlacklistGuild(guild_id=server_id)
        session.merge(blacklist)
        session.commit()
        session.close()
        await ctx.send(msg + f'✅ Successfully blacklisted guild `{server_id}`')

    @commands.is_owner()
    @commands.command(name='unblacklistguild', aliases=['unblacklist-guild'])
    async def unblacklist_guild(self, ctx, server_id: int):
        """Unblacklist a guild from using the bot"""
        session = self.bot.db.dbsession()
        try:
            check_blacklist = session.query(BlacklistGuild).filter_by(guild_id=server_id).one()
            session.delete(check_blacklist)
            session.commit()
            session.close()
            await ctx.send(f"✅ `{server_id}` successfully unblacklisted!")
        except:
            check_blacklist = None
            session.close()
            return await ctx.send(f":x: `{server_id}` isn't blacklisted!")

    @commands.is_owner()
    @commands.command(name="blacklistuser", aliases=["blacklist-user"])
    async def blacklist_user(self, ctx, userid: int, *, reason_for_blacklist: str = ""):
        """Blacklist an user from using the bot"""
        session = self.bot.db.dbsession()
        if reason_for_blacklist:
            add_blacklistuser = BlacklistUser(user_id=userid, reason=reason_for_blacklist)
        else:
            add_blacklistuser = BlacklistUser(user_id=userid, reason="No Reason Provided")
        session.merge(add_blacklistuser)
        session.commit()
        session.close()
        await ctx.send(f"✅ Successfully blacklisted user `{userid}`")

    @commands.is_owner()
    @commands.command(name="unblacklistuser", aliases=['unblacklist-user'])
    async def unblacklist_user(self, ctx, userid: int):
        """Unblacklist an user from using the bot"""
        session = self.bot.db.dbsession()
        try:
            check_if_user_blacklisted = session.query(BlacklistUser).filter_by(user_id=userid).one()
            session.delete(check_if_user_blacklisted)
            session.commit()
            session.close()
            await ctx.send(f"✅ `{userid}` successfully unblacklisted!")
        except:
            session.close()
            return await ctx.send(f"❌ `{userid}` isn't blacklisted!")

    @commands.command(name="blacklistsearch", aliases=["blacklist-search"])
    @commands.is_owner()
    async def search_blacklist(self, ctx, guild_or_user_id: int):
        """Search the blacklist to see if a user or a guild is blacklisted"""
        session = self.bot.db.dbsession()
        try:
            check_if_guild = session.query(BlacklistGuild).filter_by(guild_id=guild_or_user_id).one()
            session.close()
            await ctx.send(f"✅ Guild ID `{guild_or_user_id}` is currently blacklisted.")
        except:
            check_if_guild = None

        if check_if_guild is None:
            try:
                check_if_user = session.query(BlacklistUser).filter_by(user_id=guild_or_user_id).one()
                session.close()
                await ctx.send(f"✅ User ID `{guild_or_user_id}` is currently blacklisted.") #(Reason: {check_if_user.reason})
            except:
                check_if_user = None
        # If nothing found in either tables, return
        if check_if_user is None:
            session.close()
            await ctx.send(f"💢 No matches found for `{guild_or_user_id}`.")

    #@commands.command(name="blacklistuserlist", aliases=["blacklisteduserlist"])
    #@commands.is_owner()
    #async def blacklisted_users_list(self, ctx):
    #    """Lists blacklisted users"""
    #    session = self.bot.db.dbsession()
    #    paginator = commands.Paginator(prefix="", suffix="")
    #    for row in session.query(BlacklistUser):
    #        paginator.add_line(f"`{row.user_id}` - Reason: {row.reason}")
    #    for page in paginator.pages:
    #        await ctx.send(page)


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
        await self.bot.close()

    @commands.command()
    @commands.is_owner()
    async def dm(self, ctx, user_id: discord.Member, *, message: str):
        """Direct messages a user""" # No checks yet
        await user_id.send(message)

    @commands.command(name="addrestriction", aliases=['addrestrict'])
    @commands.is_owner()
    async def add_restriction_to_user(self, ctx, member: discord.Member, *, role: discord.Role):
        add_restriction(ctx.guild, member.id, role.id)
        await ctx.send(f"Applied {role.id} | {role.name} to {member}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        session = self.bot.db.dbsession()
        try:
            guild_blacklist = session.query(BlacklistGuild).filter_by(guild_id=guild.id).one()
            self.bot.log.info(f"Attempted to Join Blacklisted Guild | {guild.name} | ({guild.id})")
            await guild.owner.send("**Sorry, this guild is blacklisted.** To appeal your blacklist, join the support server. https://discord.gg/cDPGuYd")
            await guild.leave()
            return
        except:
            guild_blacklist = None
            msg = f"Thanks for adding me! I'm Lightning.\n"\
            f"To setup Lightning, type `l.help Configuration` in your server to begin setup.\n\n"\
            f"Need help? Either join the Lightning Discord Server. https://discord.gg/cDPGuYd or see the setup guide"\
            f" at <https://lightsage.gitlab.io/Lightning/settings/>"
            await guild.owner.send(msg)
            self.bot.log.info(f"Joined Guild | {guild.name} | ({guild.id})")
        session.close()
            


def setup(bot):
    bot.add_cog(Owner(bot))
