"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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

import asyncio
import collections
import logging
from datetime import datetime
from typing import Union

import discord
import tabulate
from discord.ext import commands, tasks

from lightning import (CommandLevel, LightningBot, LightningCog,
                       LightningContext, command, group)
from lightning.converters import InbetweenNumber
from lightning.models import PartialGuild
from lightning.utils.checks import has_guild_permissions

log = logging.getLogger(__name__)


class Stats(LightningCog):
    """Statistics related commands"""

    def __init__(self, bot: LightningBot):
        self.bot = bot

        self._command_inserts = []
        self._lock = asyncio.Lock(loop=bot.loop)
        self.bulk_command_insertion.start()

        self._socket_stats = collections.Counter()
        self._socket_lock = asyncio.Lock(loop=bot.loop)
        self.bulk_socket_stats_loop.start()

        self.number_places = (
            '\N{FIRST PLACE MEDAL}',
            '\N{SECOND PLACE MEDAL}',
            '\N{THIRD PLACE MEDAL}',
            '4\N{combining enclosing keycap}',
            '5\N{combining enclosing keycap}',
            '6\N{combining enclosing keycap}',
            '7\N{combining enclosing keycap}',
            '8\N{combining enclosing keycap}',
            '9\N{combining enclosing keycap}',
            '\N{KEYCAP TEN}')

    def cog_unload(self):
        self.bulk_command_insertion.stop()
        self.bulk_socket_stats_loop.stop()

    async def insert_command(self, ctx) -> None:
        if ctx.guild is None:
            guild_id = None
        else:
            guild_id = ctx.guild.id
        async with self._lock:
            self._command_inserts.append({
                'guild_id': guild_id,
                'channel_id': ctx.channel.id,
                'user_id': ctx.author.id,
                'used_at': ctx.message.created_at.isoformat(),
                'command_name': ctx.command.qualified_name,
                'failure': ctx.command_failed,
            })

    async def bulk_database_insert(self):
        query = """INSERT INTO commands_usage (guild_id, channel_id, user_id, used_at, command_name, failure)
                   SELECT data.guild_id, data.channel_id, data.user_id, data.used_at, data.command_name, data.failure
                   FROM jsonb_to_recordset($1::jsonb) AS
                   data(guild_id BIGINT, channel_id BIGINT, user_id BIGINT, used_at TIMESTAMP,
                        command_name TEXT, failure BOOLEAN)
                """
        if self._command_inserts:
            await self.bot.pool.execute(query, self._command_inserts)
            total = len(self._command_inserts)
            if total > 1:
                log.info(f'{total} commands were added to the database.')
            self._command_inserts.clear()

    async def bulk_socket_stats_insert(self):
        query = """INSERT INTO socket_stats (event, count)
                   VALUES ($1, $2::bigint)
                   ON CONFLICT (event)
                   DO UPDATE SET count = socket_stats.count + $2::bigint;"""
        if self._socket_stats:
            items = self._socket_stats.items()
            await self.bot.pool.executemany(query, items)
            # This gets spammy fast so it's logged at the DEBUG level
            log.debug(f"{len(self._socket_stats)} socket events were added to the database.")
            self._socket_stats.clear()

    @tasks.loop(seconds=15.0)
    async def bulk_command_insertion(self):
        async with self._lock:
            await self.bulk_database_insert()

    @LightningCog.listener()
    async def on_command_completion(self, ctx):
        await self.insert_command(ctx)

    @LightningCog.listener()
    async def on_command_error(self, ctx, error):
        await self.insert_command(ctx)

    @tasks.loop(seconds=10.0)
    async def bulk_socket_stats_loop(self):
        async with self._socket_lock:
            await self.bulk_socket_stats_insert()

    @LightningCog.listener()
    async def on_socket_response(self, msg):
        v = msg.get('t')
        if v:
            async with self._socket_lock:
                self._socket_stats[v] += 1

    async def commands_stats_guild(self, ctx: LightningContext):
        em = discord.Embed(title="Command Stats", color=0xf74b06)
        query = """SELECT COUNT(*), MIN(used_at)
                   FROM commands_usage
                   WHERE guild_id=$1;"""
        res = await self.bot.pool.fetchrow(query, ctx.guild.id)
        em.description = f"{res[0]} commands used so far."
        em.set_footer(text='Lightning has been tracking command usage since')
        em.timestamp = res[1] or datetime.utcnow()
        query = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                                      for (index, (command_name, cmd_uses)) in enumerate(records))
        if len(commands_used_des) == 0:
            commands_used_des = 'No commands used yet'
        em.add_field(name="Top Commands", value=commands_used_des)

        query = """SELECT user_id,
                        COUNT(*) as "uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   GROUP BY user_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        usage = '\n'.join(f'{self.number_places[index]}: <@!{user}> ({uses} times)'
                          for (index, (user, uses)) in enumerate(records))
        if len(usage) != 0:
            em.add_field(name="Top Command Users", value=usage)

        # Limit 5 commands as I don't want to hit the max on embed field
        # (and also makes it look ugly)
        query = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   AND used_at > (timezone('UTC', now()) - INTERVAL '1 day')
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                                      for (index, (command_name, cmd_uses)) in enumerate(records))

        if len(commands_used_des) == 0:
            commands_used_des = 'No commands used yet for today!'

        em.add_field(name="Top Commands Today", value=commands_used_des, inline=False)

        if ctx.guild.icon:
            em.set_thumbnail(url=ctx.guild.icon_url)
        await ctx.send(embed=em)

    async def command_stats_member(self, ctx: LightningContext, member):
        em = discord.Embed(title=f"Command Stats for {member}", color=0xf74b06)
        query = "SELECT COUNT(*), MIN(used_at) FROM commands_usage WHERE guild_id=$1 AND user_id=$2;"
        res = await self.bot.pool.fetchrow(query, ctx.guild.id, member.id)
        em.description = f"{res['count']} commands used so far in {ctx.guild.name}."
        # Default to utcnow() if no value
        em.set_footer(text='First command usage on')
        em.timestamp = res[1] or datetime.utcnow()
        query2 = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   AND user_id=$2
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 10;
                """
        cmds = await self.bot.pool.fetch(query2, ctx.guild.id, member.id)
        commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                                      for (index, (command_name, cmd_uses)) in enumerate(cmds))
        if len(commands_used_des) == 0:
            commands_used_des = 'No commands used yet'
        em.add_field(name="Top Commands", value=commands_used_des)

        query = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   AND used_at > (timezone('UTC', now()) - INTERVAL '1 day')
                   AND user_id=$2
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 5;
                """
        fetched = await self.bot.pool.fetch(query, ctx.guild.id, member.id)
        commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                                      for (index, (command_name, cmd_uses)) in enumerate(fetched))
        if len(commands_used_des) == 0:
            commands_used_des = 'No commands used yet for today'
        em.add_field(name="Top Commands Today", value=commands_used_des, inline=False)

        em.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=em)

    @group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    async def stats(self, ctx: LightningContext, member: discord.Member = None):
        """Sends stats about which commands are used often in the guild"""
        async with ctx.typing():
            if member is None:
                await self.commands_stats_guild(ctx)
            else:
                await self.command_stats_member(ctx, member)

    @stats.command(name="auditlog", aliases=['table', 'log'], level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    async def stats_audit_log(self, ctx: LightningContext, limit: InbetweenNumber(1, 500) = 50):
        """Shows command status for the server through a table."""
        async with ctx.typing():
            query = """SELECT command_name, channel_id, user_id, used_at
                       FROM commands_usage
                       WHERE guild_id=$1
                       ORDER BY "used_at" DESC
                       LIMIT $2;
                    """
            records = await self.bot.pool.fetch(query, ctx.guild.id, limit)
            headers = ("Command", "Channel ID", "Author ID", "Timestamp")
            content = f"Showing {len(records)} most recent entries...\n"
            table = tabulate.tabulate(records, headers=headers, tablefmt="psql")
            content += table
            await ctx.send(content)

    @stats.command(name="all")
    @commands.is_owner()
    async def stats_all(self, ctx: LightningContext):
        """Sends stats on the most popular commands used in the bot"""
        async with ctx.typing():
            query = """SELECT command_name,
                        COUNT (*) as "cmd_uses"
                       FROM commands_usage
                       GROUP BY command_name
                       ORDER BY "cmd_uses" DESC
                       LIMIT 10;
                    """
            async with self.bot.pool.acquire() as conn:
                records = await conn.fetch(query)
                total = await conn.fetchval("SELECT COUNT(*) FROM commands_usage;")
                query = "SELECT COUNT(*) FROM commands_usage WHERE used_at > (timezone('UTC', now()) - INTERVAL '1 day');"
                today_total = await conn.fetchval(query)
                embed = discord.Embed(title="Popular Commands", color=0x841d6e,
                                      description=f"Total commands used: {total}\nTotal commands used today: "
                                                  f"{today_total}")
                commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} (used {cmd_uses} times)'
                                              for (index, (command_name, cmd_uses)) in enumerate(records))
                embed.add_field(name="All Time", value=commands_used_des)
                query = """SELECT command_name,
                            COUNT (*) as "cmd_uses"
                           FROM commands_usage
                           WHERE used_at > (timezone('UTC', now()) - INTERVAL '1 day')
                           GROUP BY command_name
                           ORDER BY "cmd_uses" DESC
                           LIMIT 10;
                        """
                records = await conn.fetch(query)
            commands_used_des = '\n'.join(f'{self.number_places[index]}: {command_name} (used {cmd_uses} times)'
                                          for (index, (command_name, cmd_uses)) in enumerate(records))
            embed.add_field(name="Today", value=commands_used_des)
            await ctx.send(embed=embed)

    @command()
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    async def socketstats(self, ctx):
        """Shows a count of all tracked socket events"""
        records = await self.bot.pool.fetch("SELECT * FROM socket_stats ORDER BY count DESC;")
        table = tabulate.tabulate(records, headers=("Event", "Count"), tablefmt="psql")
        total = sum(x['count'] for x in records)
        await ctx.send(f"{total} socket events recorded.```\n{table}```")

    # There is no way to know when the bot has left or joined servers while being offline.
    # This aims to solve those issues by replacing the on_guild_join and on_guild_remove with
    # our own listeners.

    @LightningCog.listener()
    async def on_ready(self) -> None:
        records = await self.bot.pool.fetch("SELECT id, whitelisted FROM guilds WHERE left_at IS NULL;")

        for record in records:
            guild = self.bot.get_guild(record['id'])
            if guild is not None and record['whitelisted'] is False:
                await guild.leave()
                continue
            elif guild is not None:
                continue

            await self.remove_guild(record['id'])

    async def get_guild_record(self, guild_id: int) -> PartialGuild:
        record = await self.bot.pool.fetchrow("SELECT * FROM guilds WHERE id=$1", guild_id)
        return PartialGuild(record)

    async def remove_guild(self, guild: Union[int, discord.Guild, PartialGuild]) -> None:
        guild_id = getattr(guild, 'id', guild)
        await self.bot.pool.execute("UPDATE guilds SET left_at=(NOW() AT TIME ZONE 'utc') WHERE id=$1", guild_id)

        if not isinstance(guild, discord.Guild):
            guild = await self.get_guild_record(guild_id)

        self.bot.dispatch("lightning_guild_remove", guild)

    async def add_guild(self, guild: discord.Guild) -> None:
        async with self.bot.pool.acquire() as con:
            queryc = """SELECT true FROM guilds WHERE id=$1 AND left_at IS NULL;"""
            queryb = """SELECT whitelisted FROM guilds WHERE id=$1;"""  # should probably do this in a subquery
            registered = await con.fetchval(queryc, guild.id)
            whitelisted = await con.fetchval(queryb, guild.id)
            query = """INSERT INTO guilds (id, name, owner_id)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (id) DO UPDATE
                       SET name = EXCLUDED.name, owner_id = EXCLUDED.owner_id, left_at = NULL;
                    """
            await con.execute(query, guild.id, guild.name, guild.owner_id)

        if whitelisted is False:
            await guild.leave()
            # will dispatch guild_remove
            return

        if not registered:
            self.bot.dispatch("lightning_guild_add", guild)

    @LightningCog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.remove_guild(guild)

    @LightningCog.listener('on_guild_join')
    @LightningCog.listener('on_guild_available')
    async def on_guild_add(self, guild: discord.Guild) -> None:
        await self.add_guild(guild)

    @LightningCog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.name != after.name:
            await self.add_guild(after)

        if before.owner_id != after.owner_id:
            await self.add_guild(after)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Stats(bot))
