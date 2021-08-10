"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
import random
import time
import traceback

import asyncpg
import discord
import tabulate
from jishaku.codeblocks import Codeblock, codeblock_converter
from jishaku.cog import OPTIONAL_FEATURES, STANDARD_FEATURES
from jishaku.features.baseclass import Feature

from lightning import LightningBot, LightningContext, formatters
from lightning.utils import helpers
from lightning.utils import time as ltime


class CommandBug:
    def __init__(self, record: asyncpg.Record):
        self.token = record['token']
        self.traceback = record['traceback']
        self.created_at = ltime.add_tzinfo(record['created_at'])

    def __int__(self):
        return self.token

    def __repr__(self):
        return f"<CommandBug token={self.token}>"


class Owner(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    """Commands that manage the bot"""
    @Feature.Command(parent="jsk", name="leaveguild")
    async def jsk_leaveguild(self, ctx: LightningContext, guild: discord.Guild) -> None:
        """Leaves a guild that the bot is in"""
        await guild.leave()
        await ctx.send(f'Successfully left **{guild.name}** ({guild.id})')

    @Feature.Command(parent="jsk", name="pip")
    async def jsk_pip(self, ctx: LightningContext, *, argument: codeblock_converter):
        return await ctx.invoke(self.jsk_shell, argument=Codeblock(argument.language, "pip3 " + argument.content))

    @Feature.Command()
    async def fetchlog(self, ctx: LightningContext) -> None:
        """Sends the log file into the invoking author's DMs"""
        res = await helpers.dm_user(ctx.author, "Here's the current log file:", file=discord.File("lightning.log"))
        await ctx.send(helpers.ticker(res))

    @Feature.Command()
    async def blacklist(self, ctx: LightningContext) -> None:
        """Blacklisting Management"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            return

    @Feature.Command(parent="blacklist", name="adduser")
    async def blacklist_user(self, ctx: LightningContext, user_id: int, *, reason: str = "No Reason Provided") -> None:
        """Blacklist an user from using the bot"""
        blacklist = self.bot.blacklisted_users
        if user_id in self.bot.config['bot']['managers']:
            await ctx.send("You cannot blacklist a bot manager!")
            return
        elif str(user_id) in blacklist:
            await ctx.send("User already blacklisted!")
            return
        await blacklist.add(user_id, reason)
        await ctx.send(f"✅ Successfully blacklisted user `{user_id}`")

    @Feature.Command(parent="blacklist", name="removeuser")
    async def unblacklist_user(self, ctx: LightningContext, user_id: int) -> None:
        """Unblacklist an user from using the bot"""
        blacklist = self.bot.blacklisted_users
        if str(user_id) not in blacklist:
            await ctx.send("User is not blacklisted!")
            return
        await blacklist.pop(user_id)
        await ctx.send(f"✅ Successfully unblacklisted user `{user_id}`")

    @Feature.Command(parent="blacklist", name="search")
    async def search_blacklist(self, ctx: LightningContext, user_id: int) -> None:
        """Search the blacklist to see if a user is blacklisted"""
        if str(user_id) in self.bot.blacklisted_users:
            await ctx.send(f"✅ User ID `{user_id}` is currently blacklisted.\n"
                           f"Reason: {self.bot.user_blacklist.get(user_id)}")
        else:
            await ctx.send("No matches found!")

    @Feature.Command()
    async def approve(self, ctx: LightningContext, guild_id: int) -> None:
        """Approves a server.

        Server must have already existed in the database before."""
        query = "UPDATE guilds SET whitelisted='t' WHERE id=$1;"
        await self.bot.pool.execute(query, guild_id)
        await ctx.tick(True)

    @Feature.Command()
    async def unapprove(self, ctx: LightningContext, guild_id: int) -> None:
        """Unapproves a server"""
        query = "UPDATE guilds SET whitelisted='f' WHERE id=$1"
        await self.bot.pool.execute(query, guild_id)

        guild = self.bot.get_guild(guild_id)
        if guild:
            await guild.leave()

        await ctx.tick(True)

    @Feature.Command(aliases=['status'])
    async def playing(self, ctx: LightningContext, *, gamename: str = None) -> None:
        """Sets the bot's playing message."""
        if not gamename:
            await self.bot.change_presence()
            await ctx.tick(True)
            return

        await self.bot.change_presence(activity=discord.Game(name=gamename))
        await ctx.send(f'Successfully changed status to `{gamename}`')

    @Feature.Command()
    async def exit(self, ctx: LightningContext) -> None:
        """Stops the bot"""
        shutdown_messages = ['Shutting Down...', "See ya!", "RIP", "Turning off...."]
        await ctx.send(f"{helpers.Emoji.greentick} {random.choice(shutdown_messages)}")
        await self.bot.close()

    @Feature.Command()
    async def sql(self, ctx: LightningContext, *, query: codeblock_converter) -> None:
        """Run some SQL"""
        if query.count(";") > 1:
            coro = self.bot.pool.execute(query.content)
            multi_statement = True
        else:
            coro = self.bot.pool.fetch(query.content)
            multi_statement = False

        try:
            start = time.perf_counter()
            output = await coro
            dt = (time.perf_counter() - start) * 1000.0
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
            return

        if len(output) == 0:
            multi_statement = True

        if multi_statement is False:
            table = tabulate.tabulate(output, headers=list(output[0].keys()), tablefmt="psql")
            to_send = f"Took {round(dt)}ms\n{formatters.codeblock(table, language='')}"
        else:
            to_send = f"Took {round(dt)}ms\n{formatters.codeblock(output, language='')}"
        await ctx.send(to_send)

    @Feature.Command(invoke_without_command=True)
    async def bug(self, ctx: LightningContext) -> None:
        """Commands to manage the bug system"""
        await ctx.send_help("bug")

    @Feature.Command(parent="bug", name='view', aliases=['show'])
    async def viewbug(self, ctx: LightningContext, token: str) -> None:
        """Views a bug's traceback"""
        query = """SELECT traceback, created_at, token FROM command_bugs
                   WHERE token=$1;
                """
        record = await self.bot.pool.fetchrow(query, token)
        if not record:
            await ctx.send("Bug not found!")
            return

        bug = CommandBug(record)
        embed = discord.Embed(title=f"Bug {token}", timestamp=bug.created_at,
                              description=formatters.codeblock(bug.traceback))
        await ctx.send(embed=embed)

    @Feature.Command(parent="bug", name='delete', aliases=['remove', 'rm'])
    async def deletebug(self, ctx: LightningContext, token: str) -> None:
        """Deletes a bug if it exists"""
        query = "DELETE FROM command_bugs WHERE token=$1;"
        output = await self.bot.pool.execute(query, token)
        if output == "DELETE 0":
            await ctx.send("Bug not found!")
            return

        await ctx.send(f"Deleted bug {token}")

    @Feature.Command(parent="bug", name='list', aliases=['recent'])
    async def listbugs(self, ctx: LightningContext, limit: int = 10) -> None:
        """Lists the most recent bugs"""
        async with self.bot.pool.acquire() as con:
            query = """SELECT * FROM command_bugs
                       ORDER BY created_at DESC
                       LIMIT $1;
                    """
            records = await con.fetch(query, limit)
            total = await con.fetchval("SELECT COUNT(*) FROM command_bugs;")

        embed = discord.Embed(title='Recent Bugs', description='')
        for record in records:
            bug = CommandBug(record)
            preview = formatters.truncate_text((bug.traceback.splitlines())[-1], 35)
            embed.description += f"`{bug.token}`: `{preview}` {ltime.natural_timedelta(bug.created_at, brief=True)}\n"
        embed.set_footer(text=f"{total} bugs")
        await ctx.send(embed=embed)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Owner(bot=bot))
