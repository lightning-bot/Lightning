"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from __future__ import annotations

import re
import time
import traceback
from typing import TYPE_CHECKING, Any, List, Optional, Set

import asyncpg
import discord
import objgraph
import tabulate
from discord.ext import commands
from jishaku.codeblocks import Codeblock, codeblock_converter
from jishaku.cog import OPTIONAL_FEATURES, STANDARD_FEATURES
from jishaku.features.baseclass import Feature
from jishaku.repl import inspections
from jishaku.types import ContextA

from lightning import LightningBot, formatters
from lightning.utils import time as ltime

if TYPE_CHECKING:
    from lightning import LightningContext


class CommandBug:
    def __init__(self, record: asyncpg.Record):
        self.token = record['token']
        self.traceback = record['traceback']
        self.created_at = ltime.add_tzinfo(record['created_at'])

    def __repr__(self):
        return f"<CommandBug token={self.token}>"


class Owner(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    """Commands that manage the bot"""
    bot: LightningBot

    @Feature.Command(parent="jsk", name="leaveguild")
    async def jsk_leaveguild(self, ctx: LightningContext, guild: discord.Guild) -> None:
        """Leaves a guild that the bot is in"""
        await guild.leave()
        await ctx.send(f'Successfully left **{guild.name}** ({guild.id})')

    @Feature.Command(parent="jsk", name="pip")
    async def jsk_pip(self, ctx: LightningContext, *, argument: codeblock_converter):
        return await ctx.invoke(self.jsk_shell, argument=Codeblock(argument.language, f"pip3 {argument.content}"))

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

        if guild := self.bot.get_guild(guild_id):
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
            table = tabulate.tabulate(output, headers="keys", tablefmt="psql")
            content = f"Took {round(dt)}ms\n{formatters.codeblock(table, language='')}"
        else:
            content = f"Took {round(dt)}ms\n{formatters.codeblock(output, language='')}"

        await ctx.send(content)

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

    @Feature.Command(parent="jsk", name="objgraph")
    async def jsk_objgraph(self, ctx: LightningContext) -> None:
        """Tells you what objects are currently in memory"""
        fmt = tabulate.tabulate(objgraph.most_common_types())
        await ctx.send(formatters.codeblock(fmt))

    SLASH_COMMAND_ERROR = re.compile(r"In ((?:\d+\.[a-z]+\.?)+)")

    @Feature.Command(parent="jsk", name="sync")
    async def jsk_sync(self, ctx: ContextA, *targets: str):
        """
        Sync global or guild application commands to Discord.
        """
        if not self.bot.application_id:
            await ctx.send("Cannot sync when application info not fetched")
            return

        paginator = commands.Paginator(prefix='', suffix='')

        guilds_set: Set[Optional[int]] = set()
        for target in targets:
            if target == '$':
                guilds_set.add(None)
            elif target == '*':
                guilds_set |= set(self.bot.tree._guild_commands.keys())  # type: ignore  # pylint: disable=protected-access  # noqa: E501
            elif target == '.':
                if ctx.guild:
                    guilds_set.add(ctx.guild.id)
                else:
                    await ctx.send("Can't sync guild commands without guild information")
                    return
            else:
                try:
                    guilds_set.add(int(target))
                except ValueError as error:
                    raise commands.BadArgument(f"{target} is not a valid guild ID") from error

        if not targets:
            guilds_set.add(None)

        guilds: List[Optional[int]] = list(guilds_set)
        guilds.sort(key=lambda g: (g is not None, g))

        for guild in guilds:
            slash_commands = self.bot.tree._get_all_commands(  # type: ignore  # pylint: disable=protected-access
                guild=discord.Object(guild) if guild else None
            )
            translator = getattr(self.bot.tree, 'translator', None)
            if translator:
                payload = [await command.get_translated_payload(tree=self.bot.tree, translator=translator) for command in slash_commands]  # noqa: E501
            else:
                payload = [command.to_dict(tree=self.bot.tree) for command in slash_commands]

            try:
                if guild is None:
                    data = await self.bot.http.bulk_upsert_global_commands(self.bot.application_id, payload=payload)
                else:
                    data = await self.bot.http.bulk_upsert_guild_commands(self.bot.application_id, guild, payload=payload)  # noqa: E501

                synced = [
                    discord.app_commands.AppCommand(data=d, state=ctx._state)  # type: ignore  # pylint: disable=protected-access,no-member  # noqa: E501
                    for d in data
                ]

            except discord.HTTPException as error:
                # It's diagnosis time
                error_lines: List[str] = []
                for line in str(error).split("\n"):
                    error_lines.append(line)

                    try:
                        match = self.SLASH_COMMAND_ERROR.match(line)
                        if not match:
                            continue

                        pool = slash_commands
                        selected_command = None
                        name = ""
                        parts = match.group(1).split('.')
                        assert len(parts) % 2 == 0

                        for part_index in range(0, len(parts), 2):
                            index = int(parts[part_index])
                            # prop = parts[part_index + 1]

                            if pool:
                                # If the pool exists, this should be a subcommand
                                selected_command = pool[index]  # type: ignore
                                name += selected_command.name + " "

                                if hasattr(selected_command, '_children'):  # type: ignore
                                    pool = list(selected_command._children.values())  # type: ignore  # pylint: disable=protected-access  # noqa: E501
                                else:
                                    pool = None
                            else:
                                # Otherwise, the pool has been exhausted, and this likely is referring to a parameter
                                param = list(selected_command._params.keys())[index]  # type: ignore  # pylint: disable=protected-access  # noqa: E501
                                name += f"(parameter: {param}) "

                        if selected_command:
                            to_inspect: Any = None

                            if hasattr(selected_command, 'callback'):  # type: ignore
                                to_inspect = selected_command.callback  # type: ignore
                            elif isinstance(selected_command, commands.Cog):
                                to_inspect = type(selected_command)

                            try:
                                error_lines.append(''.join([
                                    "\N{MAGNET} This is likely caused by: `",
                                    name,
                                    "` at ",
                                    str(inspections.file_loc_inspection(to_inspect)),  # type: ignore
                                    ":",
                                    str(inspections.line_span_inspection(to_inspect)),  # type: ignore
                                ]))
                            except Exception:  # pylint: disable=broad-except
                                error_lines.append(f"\N{MAGNET} This is likely caused by: `{name}`")

                    except Exception as diag_error:  # pylint: disable=broad-except
                        error_lines.append(f"\N{MAGNET} Couldn't determine cause: {type(diag_error).__name__}: "
                                           f"{diag_error}")

                error_text = '\n'.join(error_lines)

                if guild:
                    paginator.add_line(f"\N{WARNING SIGN} `{guild}`: {error_text}", empty=True)
                else:
                    paginator.add_line(f"\N{WARNING SIGN} Global: {error_text}", empty=True)
            else:
                if guild:
                    paginator.add_line(f"\N{SATELLITE ANTENNA} `{guild}` Synced {len(synced)} guild commands",
                                       empty=True)
                else:
                    paginator.add_line(f"\N{SATELLITE ANTENNA} Synced {len(synced)} global commands", empty=True)

        for page in paginator.pages:
            await ctx.send(page)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Owner(bot=bot))
    if bot.config['tokens']['sentry']:
        bot.remove_command("bug")
