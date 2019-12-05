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
import io
import json
import os
import random
import shutil
import textwrap
import traceback
from contextlib import redirect_stdout

import bolt.http
import bolt.misc
import discord
import toml
from bolt.paginator import TextPages
from discord.ext import commands

from utils.checks import is_bot_manager


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

    def blacklist_dump(self, filepath, json_returned):
        os.makedirs("config", exist_ok=True)
        with open(f"config/{filepath}.json", "w") as f:
            return json.dump(json_returned, f)

    def grab_blacklist_guild(self):
        if os.path.isfile("config/guild_blacklist.json"):
            with open("config/guild_blacklist.json", "r") as blacklist:
                return json.load(blacklist)
        else:
            return {}

    @commands.is_owner()
    @commands.command()
    async def fetchlog(self, ctx):
        """Returns log"""
        await ctx.message.add_reaction("✅")
        try:
            await ctx.author.send("Here's the current log file:",
                                  file=discord.File(f"{self.bot.script_name}.log"))
        except discord.errors.Forbidden:
            return await ctx.send("💢 I couldn't send the log file in your DMs")

    @commands.check(is_bot_manager)
    @commands.command(aliases=['getguildprefix', 'ggp'])
    async def getguildprefixes(self, ctx, guildid: int):
        """Returns the prefixes set for a certain guild"""
        cfg = self.bot.get_cog('Configuration')
        if cfg:
            msg = f"Prefixes for {guildid}\n\n"
            prefixes = await cfg.get_guild_prefixes(guildid)
            for p in prefixes:
                msg += f"- {p}\n"
        else:
            msg = "Configuration Cog not loaded!"
        await ctx.send("```" + msg + "```")

    @commands.group()
    @commands.check(is_bot_manager)
    async def blacklist(self, ctx):
        """Blacklisting Management"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @commands.check(is_bot_manager)
    @blacklist.command(name='addguild', aliases=['guildadd'])
    async def blacklist_guild(self, ctx, server_id: int, *, reason: str = ""):
        """Blacklist a guild from using the bot"""
        guild = self.bot.get_guild(server_id)
        if guild is None:
            msg = "**Note**: Lightning is not in that guild. This is a preventive blacklist.\n"
        else:
            msg = ""
            await guild.leave()
        bl = self.grab_blacklist_guild()
        if str(server_id) in bl:
            return await ctx.send(f"Guild is already blacklisted")
        if reason:
            tr = reason
        else:
            tr = "No Reason Provided"
        bl[str(server_id)] = tr
        self.blacklist_dump("guild_blacklist", bl)
        await ctx.send(msg + f'✅ Successfully blacklisted guild `{server_id}`')

    @commands.check(is_bot_manager)
    @blacklist.command(name='removeguild', aliases=['unblacklist-guild'])
    async def unblacklist_guild(self, ctx, server_id: int):
        """Unblacklist a guild from using the bot"""
        bl = self.grab_blacklist_guild()
        if str(server_id) not in bl:
            return await ctx.send(f"Guild is not blacklisted!")
        bl.pop(str(server_id))
        self.blacklist_dump("guild_blacklist", bl)
        await ctx.send(f"✅ `{server_id}` successfully unblacklisted!")

    @commands.check(is_bot_manager)
    @blacklist.command(name="adduser", aliases=["blacklist-user"])
    async def blacklist_user(self, ctx, userid: int, *, reason_for_blacklist: str = ""):
        """Blacklist an user from using the bot"""
        bl = self.grab_blacklist()
        if userid in self.bot.config['bot']['managers']:
            return await ctx.send("You cannot blacklist a bot manager!")
        elif str(userid) in bl:
            return await ctx.send("User already blacklisted!")
        if reason_for_blacklist:
            rb = reason_for_blacklist
        else:
            rb = "No Reason Provided"
        bl[str(userid)] = rb
        self.blacklist_dump("user_blacklist", bl)
        await ctx.send(f"✅ Successfully blacklisted user `{userid}`")

    @commands.check(is_bot_manager)
    @blacklist.command(name="removeuser", aliases=['unblacklist-user'])
    async def unblacklist_user(self, ctx, userid: int):
        """Unblacklist an user from using the bot"""
        bl = self.grab_blacklist()
        if str(userid) not in bl:
            return await ctx.send("User is not blacklisted!")
        bl.pop(str(userid))
        self.blacklist_dump("user_blacklist", bl)
        await ctx.send(f"✅ Successfully unblacklisted user `{userid}`")

    @commands.check(is_bot_manager)
    @blacklist.command(name="search")
    async def search_blacklist(self, ctx, id: int):
        """Search the blacklist to see if a user or a guild is blacklisted"""
        bl = self.grab_blacklist()
        if str(id) in bl:
            return await ctx.send(f"✅ User ID `{id}` is currently blacklisted.\n"
                                  f"Reason: {bl[str(id)]}")
        bl = self.grab_blacklist_guild()
        if str(id) in bl:
            return await ctx.send(f"✅ Guild ID `{id}` is currently blacklisted.\n"
                                  f"Reason: {bl[str(id)]}")
        await ctx.send("No matches found!")

    @commands.is_owner()
    @commands.command()
    async def leaveguild(self, ctx, server_id: int):
        """Leaves the guild via ID"""
        server = self.bot.get_guild(server_id)
        if server is None:
            return await ctx.send('I\'m not in this server.')
        await server.leave()
        await ctx.send(f'Successfully left {server.name}')

    # RoboDanny's eval command. (even though Jishaku exists)
    # MIT Licensed.
    # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py
    @commands.is_owner()
    @commands.command(name='eval')
    async def _eval(self, ctx, *, code: str):
        """Evaluates some code, Owner only."""
        code = code.strip('` ')

        env = {'bot': self.bot,
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
               '_p': self.previous_eval_code}
        env.update(globals())

        self.bot.log.info(f"Evaling {repr(code)}:")
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except Exception:
                pass

            if ret is None:
                if value:
                    await ctx.send(f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.is_owner()
    @commands.command(name="pull-exit", aliases=['pe'])
    async def pull_exit(self, ctx):
        """Git Pulls and then exits"""
        await ctx.send("Git Pulling....")
        await ctx.invoke(self.bot.get_command('bolt pull'))
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
        tmp = await ctx.send("I\'m figuring this out.")
        async with ctx.typing():
            out = await bolt.misc.call_shell("pip3 list --outdated")
        await tmp.delete()
        pages = TextPages(ctx, f"{out}")
        await pages.paginate()

    @commands.is_owner()
    @pip.command(name='dpy', aliases=['discordpy'])
    async def updatedpy(self, ctx):
        """Updates discord.py. Use .pip chkupdate
        to see if there are updates to any packages."""
        sh_out = await bolt.misc.call_shell("pip3 install --upgrade discord.py")
        pages = TextPages(ctx, f"{sh_out}")
        await pages.paginate()

    @commands.is_owner()
    @pip.command()
    async def freeze(self, ctx):
        """Returns a list of pip packages installed"""
        sh_out = await bolt.misc.call_shell("pip3 freeze -l")
        pages = TextPages(ctx, f"{sh_out}")
        await pages.paginate()

    @commands.is_owner()
    @pip.command()
    async def uninstall(self, ctx, package: str):
        """Uninstalls a package. (Use with care.)"""
        sh_out = await bolt.misc.call_shell(f"pip3 uninstall -y {package}")
        pages = TextPages(ctx, f"{sh_out}")
        await pages.paginate()

    @commands.command(aliases=['status'])  # 'play'
    @commands.is_owner()
    async def playing(self, ctx, *, gamename: str = ""):
        """Sets the bot's playing message. Owner only."""
        await self.bot.change_presence(activity=discord.Game(name=gamename))
        await ctx.send(f'Successfully changed status to `{gamename}`')

    @commands.command(aliases=['bye', 'exit'])
    @commands.is_owner()
    async def stop(self, ctx):
        """Stop the Bot."""
        shutdown_messages = ['Shutting Down...', "See ya!", "RIP", "Turning off...."]
        await ctx.send(f"👋 {random.choice(shutdown_messages)}")
        await self.bot.db.close()
        await self.bot.aiosession.close()
        await self.bot.logout()

    @commands.group()
    @commands.is_owner()
    async def reload(self, ctx):
        """Reloads internal cached dicts.

        All commands besides config under the reload group have a dump argument,
        to dump pass a truthy value"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help('reload')

    @reload.command(name="config")
    async def r_config(self, ctx):
        with open("config.toml", "r") as c:
            self.bot.config = toml.load(c)
        await ctx.send("\N{OK HAND SIGN}")

    @commands.command()
    @commands.is_owner()
    async def dm(self, ctx, user_id: discord.Member, *, message: str):
        """Direct messages a user"""  # No checks yet
        await user_id.send(message)

    @commands.command()
    @commands.check(is_bot_manager)
    async def curl(self, ctx, url: str):
        """Curls a site, returning its contents."""
        text = await bolt.http.get(self.bot.aiosession, url)
        pages = TextPages(ctx, f"{text}")
        await pages.paginate()

    @commands.command(aliases=['list-cogs'])
    @commands.is_owner()
    async def listcogs(self, ctx):
        """Lists the currently loaded cogs"""
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line("✅ __Loaded Cogs:__")
        for cog in list(self.bot.extensions.keys()):
            paginator.add_line(f"- {cog}")

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
        bl = self.grab_blacklist_guild()
        if str(guild.id) in bl:
            self.bot.log.info(f"Attempted to Join Blacklisted Guild | {guild.name} | ({guild.id})")
            try:
                await guild.owner.send("**Sorry, this guild is blacklisted.** To appeal your blacklist, "
                                       "join the support server. https://discord.gg/cDPGuYd")
            except discord.Forbidden:
                pass
            await guild.leave()
            return

        else:
            # msg = f"Thanks for adding me! I'm Lightning.\n\n"\
            #      f"To setup Lightning, type `l.help Configuration` in your server to begin setup.\n\n"\
            #      f"Need help? Either join the Lightning Discord Server. https://discord.gg/cDPGuYd"\
            #      f" or see the setup guide"\
            #      f" at <https://lightsage.gitlab.io/lightning/setup/>"
            # try:
            #    await guild.owner.send(msg)
            # except discord.Forbidden:
            #    pass
            self.bot.log.info(f"Joined Guild | {guild.name} | ({guild.id})")


def setup(bot):
    bot.add_cog(Owner(bot))
