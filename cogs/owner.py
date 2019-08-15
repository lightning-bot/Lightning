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

import discord
from discord.ext import commands
import traceback
import inspect
import re
import asyncio
from database import BlacklistGuild
from utils.restrictions import add_restriction
import random
import config
from utils.bot_mgmt import add_botmanager, check_if_botmgmt, remove_botmanager, read_bm
from utils.paginators_jsk import paginator_reg
import os
import json
import shutil
from utils.custom_prefixes import get_guildid_prefixes

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_eval_result = None
        self.previous_eval_code = None
        self.bot.get_blacklist = self.grab_blacklist

    def grab_blacklist(self):
        os.makedirs("config", exist_ok=True)
        if os.path.isfile("config/user_blacklist.json"):
            with open("config/user_blacklist.json", "r") as blacklist:
                return json.load(blacklist)
        else:
            return {}

    def blacklist_dump(self, json_returned):
        os.makedirs("config", exist_ok=True)
        with open("config/user_blacklist.json", "w") as f:
            return json.dump(json_returned, f)

    @commands.is_owner()
    @commands.command(aliases=['sh'])
    async def shell(self, ctx, *, command: str):
        """Runs a command in the terminal/shell"""
        shell_out = await self.bot.call_shell(command)
        sliced_message = await self.bot.slice_message(shell_out)
        await paginator_reg(self.bot, ctx, size=1985, page_list=sliced_message)
    
    @commands.is_owner()
    @commands.command()
    async def fetchlog(self, ctx):
        """Returns log"""
        log_channel = self.bot.get_channel(config.error_channel)
        await ctx.message.add_reaction("✅")
        try:
            await ctx.author.send("Here's the current log file:", 
                                  file=discord.File(f"{self.bot.script_name}.log"))
        except discord.errors.Forbidden:
            await ctx.send("💢 I couldn't send the log file in your DMs so I "
                           "sent it to the bot\'s logging channel.")
            await log_channel.send("Here's the current log file:", 
                                   file=discord.File(f"{self.bot.script_name}.log"))
    
    @commands.check(check_if_botmgmt)
    @commands.command(name="fetchguilduserlog")
    async def getmodlogjson(self, ctx, guild_id: int):
        """Gets the guild id's userlog.json file"""
        try:
            await ctx.send(f"Here's the userlog.json for `{guild_id}`", 
                           file=discord.File(f"config/{guild_id}/userlog.json"))
        except:
            await ctx.send(f"`{guild_id}` doesn't have a userlog.json yet. Check back later.")

    @commands.check(check_if_botmgmt)
    @commands.command(aliases=['getguildprefix', 'ggp'])
    async def getguildprefixes(self, ctx, guildid: int):
        """Returns the prefixes set for a certain guild"""
        msg = f"Prefixes for {guildid}\n\n"
        if "prefixes" in get_guildid_prefixes(guildid):
            for p in get_guildid_prefixes(guildid)["prefixes"]:
                msg += f"- {p}\n"
        else:
            msg = "No Prefixes!"
        await ctx.send("```" + msg + "```")

    @commands.group()
    @commands.check(check_if_botmgmt)
    async def blacklist(self, ctx):
        """Blacklisting Management"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)
    
    @commands.check(check_if_botmgmt)
    @blacklist.command(name='addguild', aliases=['guildadd'])
    async def blacklist_guild(self, ctx, server_id: int):
        """Blacklist a guild from using the bot"""
        guild = self.bot.get_guild(server_id)
        if guild is None:
            msg = "**Note**: Lightning is not in that guild. This is a preventive blacklist.\n"
        else:
            msg = ""
            await guild.leave()

        session = self.bot.dbsession()
        blacklist = BlacklistGuild(guild_id=server_id)
        session.merge(blacklist)
        session.commit()
        session.close()
        await ctx.send(msg + f'✅ Successfully blacklisted guild `{server_id}`')

    @commands.check(check_if_botmgmt)
    @blacklist.command(name='removeguild', aliases=['unblacklist-guild'])
    async def unblacklist_guild(self, ctx, server_id: int):
        """Unblacklist a guild from using the bot"""
        session = self.bot.dbsession()
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

    @commands.check(check_if_botmgmt)
    @blacklist.command(name="adduser", aliases=["blacklist-user"])
    async def blacklist_user(self, ctx, userid: int, *, reason_for_blacklist: str = ""):
        """Blacklist an user from using the bot"""
        bl = self.grab_blacklist()
        if read_bm(userid):
            return await ctx.send("You cannot blacklist a bot manager!")
        elif str(userid) in bl:
            return await ctx.send("User already blacklisted!")
        if reason_for_blacklist:
            rb = reason_for_blacklist
        else:
            rb = "No Reason Provided"
        bl[str(userid)] = rb
        self.blacklist_dump(bl)
        await ctx.send(f"✅ Successfully blacklisted user `{userid}`")

    @commands.check(check_if_botmgmt)
    @blacklist.command(name="removeuser", aliases=['unblacklist-user'])
    async def unblacklist_user(self, ctx, userid: int):
        """Unblacklist an user from using the bot"""
        bl = self.grab_blacklist()
        if str(userid) not in bl:
            return await ctx.send("User is not blacklisted!")
        bl.pop(str(userid))
        self.blacklist_dump(bl)
        await ctx.send(f"✅ Successfully unblacklisted user `{userid}`")

    @commands.check(check_if_botmgmt)
    @blacklist.command(name="search")
    async def search_blacklist(self, ctx, guild_or_user_id: int):
        """Search the blacklist to see if a user or a guild is blacklisted"""
        session = self.bot.dbsession()
        try:
            check_if_guild = session.query(BlacklistGuild).filter_by(guild_id=guild_or_user_id).one()
            session.close()
            await ctx.send(f"✅ Guild ID `{guild_or_user_id}` is currently blacklisted.")
        except:
            check_if_guild = None
            session.close()

        if check_if_guild is None:
            try:
                bl = self.grab_blacklist()
                if str(guild_or_user_id) in bl:
                    await ctx.send(f"✅ User ID `{guild_or_user_id}` is currently blacklisted.\n"
                                   f"Reason: {bl[str(guild_or_user_id)]}")
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
    #    session = self.bot.dbsession()
    #    paginator = commands.Paginator(prefix="", suffix="")
    #    for row in session.query(BlacklistUser):
    #        paginator.add_line(f"`{row.user_id}` - Reason: {row.reason}")
    #    for page in paginator.pages:
    #        await ctx.send(page)

    @commands.is_owner()
    @commands.command()
    async def logout(self, ctx):
        """Logout the bot"""
        await ctx.send('Logging out now...')
        await asyncio.sleep(5.0)
        await self.bot.logout()

    @commands.is_owner()
    @commands.command()
    async def leaveguild(self, ctx, server_id: int):
        """Leaves the guild via ID"""
        server = self.bot.get_guild(server_id)
        if server is None:
            return await ctx.send('I\'m not in this server.')
        await server.leave()
        await ctx.send(f'Successfully left {server.name}')
    
    # Robocop-ng's eval commands. MIT Licensed. 
    # https://github.com/reswitched/robocop-ng/blob/master/LICENSE
    @commands.is_owner()
    @commands.command(name='eval')
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
    @git.command()
    @commands.guild_only()
    async def pull(self, ctx):
        """Pull new changes from GitHub."""
        msg = await ctx.send("<a:loading:568232137090793473> Pulling changes...")
        output = await self.bot.call_shell("git pull")
        await msg.edit(content=f'📥 Pulled Changes:\n```diff\n{output}\n```')

    @commands.is_owner()
    @git.command(aliases=['pr'])
    @commands.guild_only()
    async def pullreload(self, ctx):
        """Pull and reload the cogs automatically."""
        msg = await ctx.send("<a:loading:568232137090793473> Pulling changes...")
        output = await self.bot.call_shell("git pull")
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
        output = await self.bot.call_shell("git pull")
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

    @commands.is_owner()
    @git.command(name="pull-exit", aliases=['pe'])
    async def pull_exit(self, ctx):
        """Git Pulls and then exits"""
        await ctx.send("Git Pulling....")
        await ctx.invoke(self.bot.get_command('git pull'))
        await asyncio.sleep(10.0)
        await ctx.send("Exiting...")
        await ctx.invoke(self.bot.get_command('exit'))

    @commands.is_owner()
    @commands.group()
    async def pip(self, ctx):
        """Helper commands to assist with pip things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @commands.is_owner()
    @pip.command(name="check-updates", 
                 aliases=['chkupdate', 'cupdate', 'chku'])
    async def check_updates(self, ctx):
        """Checks to see which packages are outdated"""
        await ctx.send("I\'m figuring this out.")
        out = await self.bot.call_shell("pip3 list --outdated")
        slice_msg = await self.bot.slice_message(out,
                                                 prefix="```",
                                                 suffix="```")
        for msg in slice_msg:
            await ctx.send(msg)

    @commands.is_owner()
    @pip.command(name='dpy', aliases=['discordpy'])
    async def updatedpy(self, ctx):
        """Updates discord.py. Use .pip chkupdate to see if there are updates to any packages."""
        sh_out = await self.bot.call_shell("pip3 install --upgrade discord.py")
        slice_msg = await self.bot.slice_message(sh_out,
                                                 prefix="```",
                                                 suffix="```")
        for msg in slice_msg:
            await ctx.send(msg)

    @commands.is_owner()
    @pip.command()
    async def freeze(self, ctx):
        """Returns a list of pip packages installed"""
        sh_out = await self.bot.call_shell("pip3 freeze -l")
        slice_msg = await self.bot.slice_message(sh_out,
                                                 prefix="```",
                                                 suffix="```")
        for msg in slice_msg:
            await ctx.send(msg)

    @commands.is_owner()
    @pip.command()
    async def uninstall(self, ctx, package: str):
        """Uninstalls a package. (Use with care.)"""
        sh_out = await self.bot.call_shell(f"pip3 uninstall -y {package}")
        slice_msg = await self.bot.slice_message(sh_out,
                                                 prefix="```",
                                                 suffix="```")
        for msg in slice_msg:
            await ctx.send(msg)
            
    @commands.command(aliases=['status']) #'play'
    @commands.is_owner()
    async def playing(self, ctx, *, gamename: str = ""):
        """Sets the bot's playing message. Owner only."""
        await self.bot.change_presence(activity=discord.Game(name=f'{" ".join(gamename)}'))
        await ctx.send(f'Successfully changed status to `{gamename}`')

    @commands.command(aliases=['bye', 'exit'])
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

    @commands.check(check_if_botmgmt)
    @commands.group(invoke_without_command=True)
    async def curl(self, ctx, url: str):
        """Curls a site"""
        text = await self.bot.aioget(url)
        if len(text) > 1990: # Safe Number
            haste_url = await self.bot.haste(text)
            return await ctx.send(f"Message exceeded character limit. See the haste {haste_url}")
        await ctx.send(f"```md\n{text}```")

    @commands.check(check_if_botmgmt)
    @curl.command(name='raw')
    async def curl_raw(self, ctx, url: str):
        text = await self.bot.aiogetbytes(url)

        sliced_message = await self.bot.slice_message(f"{url}\n\n{text}",
                                                      prefix="```",
                                                      suffix="```")

        for msg in sliced_message:
            await ctx.send(msg)

    @commands.is_owner()
    @commands.command()
    async def addbotmanager(self, ctx, uid: discord.Member):
        """Adds a user ID to the bot manager list"""
        add_botmanager(uid.id)
        await ctx.send(f"{uid} is now a bot manager")

    @commands.is_owner()
    @commands.command()
    async def removebotmanager(self, ctx, uid: discord.Member):
        """Removes a user ID from the bot manager list"""
        remove_botmanager(uid.id)
        await ctx.send(f"{uid} is no longer a bot manager")

    @commands.is_owner()
    @commands.command()
    async def fetchdb(self, ctx):
        """Fetches the database files"""
        await ctx.send(file=discord.File("config/powerscron.sqlite3"))
        await ctx.send(file=discord.File("config/database.sqlite3"))

    @commands.command(name='load')
    @commands.is_owner()
    async def c_load(self, ctx, *, cog: str):
        """Load a Cog."""
        cogx = "cogs." + cog
        if cogx in self.bot.cog_loaded:
            return await ctx.send(f'`{cogx}` is already loaded.')
        try:
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            self.bot.cog_unloaded.append("cogs." + cog)
            await ctx.send(f'💢 There was an error loading the cog \n'
                           f'**ERROR:** ```{type(e).__name__} - {e}```')
        else:
            self.bot.cog_loaded.append("cogs." + cog)
            self.bot.cog_unloaded.remove("cogs." + cog)
            self.bot.log.info(f"{ctx.author} loaded the cog `{cog}`")
            await ctx.send(f'✅ Successfully loaded `cogs.{cog}`')

    @commands.command(name='unload')
    @commands.is_owner()
    async def c_unload(self, ctx, *, cog: str):
        """Unloads a Cog."""
        try:
            self.bot.unload_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error unloading the cog \n'
                           f'**ERROR:** ```{type(e).__name__} - {e}```')
        else:
            self.bot.log.info(f"{ctx.author} unloaded the cog `{cog}`")
            self.bot.cog_unloaded.append("cogs." + cog)
            self.bot.cog_loaded.remove("cogs." + cog)    
            await ctx.send(f'✅ Successfully unloaded `cogs.{cog}`')

    @commands.command(name='reload')
    @commands.is_owner()
    async def c_reload(self, ctx, *, cog: str):
        """Reload a Cog."""
        try:
            self.bot.unload_extension("cogs." + cog)
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            self.bot.cog_loaded.remove("cogs." + cog)
            self.bot.cog_unloaded.append("cogs." + cog)
            return await ctx.send(f'💢 There was an error reloading the cog \n'
                           f'**ERROR:** ```{type(e).__name__} - {e}```')
        else:
            self.bot.log.info(f"{ctx.author} reloaded the cog `{cog}`")  
            self.bot.cog_loaded.remove("cogs." + cog)
            self.bot.cog_loaded.append("cogs." + cog)   
            await ctx.send(f'✅ Successfully reloaded `cogs.{cog}`')

    @commands.command(aliases=['list-cogs'])
    @commands.is_owner()
    async def listcogs(self, ctx):
        """Lists the currently loaded cogs"""
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line("✅ __Loaded Cogs:__")
        for cog in self.bot.cog_loaded:
            paginator.add_line(f"- {cog}")
        
        paginator.add_line(":x: __Unloaded Cogs:__")
        if len(self.bot.cog_unloaded) != 0:
            for cog in self.bot.cog_unloaded:
                paginator.add_line(f"- {cog}")
        else:
            paginator.add_line("None")

        for page in paginator.pages:
            await ctx.send(page) 

    @commands.command(aliases=['rgf'])
    @commands.is_owner()
    async def removeguildfolder(self, ctx, guildid: int):
        """Removes a guild's configuration folder"""
        if os.path.isdir(f"config/{guildid}/"):
            # Remove the directory
            shutil.rmtree(f"config/{guildid}/")
            await ctx.send(f"Removed {guildid}")
        else:
            return await ctx.send("Invalid Path!")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        session = self.bot.dbsession()
        try:
            session.query(BlacklistGuild).filter_by(guild_id=guild.id).one()
            self.bot.log.info(f"Attempted to Join Blacklisted Guild | {guild.name} | ({guild.id})")
            try:
                await guild.owner.send("**Sorry, this guild is blacklisted.** To appeal your blacklist, "
                                       "join the support server. https://discord.gg/cDPGuYd")
            except discord.Forbidden:
                pass
            await guild.leave()
            return
        except:
            guild_blacklist = None

        if guild_blacklist is None:
            msg = f"Thanks for adding me! I'm Lightning.\n"\
                   "Discord's API Terms of Service requires me to tell you that I "\
                   "log command usage and errors to a special channel.\n**Only commands and"\
                   " errors are logged, no messages are logged, ever.**\n\n"\
                  f"To setup Lightning, type `l.help Configuration` in your server to begin setup.\n\n"\
                  f"Need help? Either join the Lightning Discord Server. https://discord.gg/cDPGuYd"\
                  f" or see the setup guide"\
                  f" at <https://lightsage.gitlab.io/lightning/setup/>"
            try:
                await guild.owner.send(msg)
            except discord.Forbidden:
                pass
            self.bot.log.info(f"Joined Guild | {guild.name} | ({guild.id})")
        session.close()
            
def setup(bot):
    bot.add_cog(Owner(bot))