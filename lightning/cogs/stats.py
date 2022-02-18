"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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

import asyncio
import collections
import logging
from typing import TYPE_CHECKING

import discord
import tabulate
from discord.ext import commands, tasks

from lightning import (CommandLevel, LightningCog, LightningContext, command,
                       group)
from lightning.converters import InbetweenNumber
from lightning.utils.checks import has_guild_permissions
from lightning.utils.emitters import WebhookEmbedEmitter
from lightning.utils.modlogformats import base_user_format

if TYPE_CHECKING:
    from typing import Union

    from lightning import LightningBot
    from lightning.models import PartialGuild

log: logging.Logger = logging.getLogger(__name__)


class Stats(LightningCog):
    """Statistics related commands"""

    def __init__(self, bot: LightningBot):
        self.bot = bot

        self._command_inserts = []
        self._lock = asyncio.Lock()
        self.bulk_command_insertion.start()

        self._socket_stats = collections.Counter()
        self._socket_lock = asyncio.Lock()
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

    def cog_unload(self) -> None:
        self.bulk_command_insertion.stop()
        self.bulk_socket_stats_loop.stop()

        if hasattr(self, 'guild_stats_bulker'):
            self.guild_stats_bulker.close()

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

    async def bulk_database_insert(self) -> None:
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

    async def bulk_socket_stats_insert(self) -> None:
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
    async def on_socket_event_type(self, event):
        async with self._socket_lock:
            self._socket_stats[event] += 1

    def format_stat_description(self, records, *, none_msg: str = "Nothing found yet."):
        x = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                      for (index, (command_name, cmd_uses)) in enumerate(records))

        if len(x) == 0:
            return none_msg

        return x

    async def commands_stats_guild(self, ctx: LightningContext):
        em = discord.Embed(title="Command Stats", color=0xf74b06)
        query = """SELECT COUNT(*), MIN(used_at)
                   FROM commands_usage
                   WHERE guild_id=$1;"""
        res = await self.bot.pool.fetchrow(query, ctx.guild.id)
        em.description = f"{res[0]} commands used so far."
        em.set_footer(text='Tracking command usage since')
        em.timestamp = res[1] or discord.utils.utcnow()
        query = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        em.add_field(name="Top Commands", value=self.format_stat_description(records, none_msg="No commands used yet."))

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
        em.add_field(name="Top Commands Today",
                     value=self.format_stat_description(records, none_msg="No commands used yet."), inline=False)

        query = """SELECT channel_id,
                        COUNT(*) as "uses"
                   FROM commands_usage
                   WHERE guild_id=$1
                   AND channel_id IS NOT NULL
                   GROUP BY channel_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        fmt = []
        for (index, (channel_id, _)) in enumerate(records):
            channel = getattr(ctx.guild.get_channel(channel_id), "mention", "Deleted channel")
            fmt.append(f"{self.number_places[index]}: {channel}")
        fmt = "\n".join(fmt)
        if len(fmt) != 0:
            em.add_field(name="Top Channels Used", value=fmt, inline=False)

        if ctx.guild.icon:
            em.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=em)

    async def command_stats_member(self, ctx: LightningContext, member):
        em = discord.Embed(title=f"Command Stats for {member}", color=0xf74b06)
        query = "SELECT COUNT(*), MIN(used_at) FROM commands_usage WHERE guild_id=$1 AND user_id=$2;"
        res = await self.bot.pool.fetchrow(query, ctx.guild.id, member.id)
        em.description = f"{res['count']} commands used so far in {ctx.guild.name}."

        em.set_footer(text='First command usage on')
        em.timestamp = res[1] or discord.utils.utcnow()
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
        em.add_field(name="Top Commands", value=self.format_stat_description(cmds, none_msg="No commands used yet."))

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
        records = await self.bot.pool.fetch(query, ctx.guild.id, member.id)
        em.add_field(name="Top Commands Today",
                     value=self.format_stat_description(records, none_msg="No commands used yet."), inline=False)

        em.set_thumbnail(url=member.avatar.url)
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
        """Shows command stats for the server through a table."""
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
                query = """SELECT COUNT(*) FROM commands_usage
                           WHERE used_at > (timezone('UTC', now()) - INTERVAL '1 day');"""
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
        table = tabulate.tabulate(records, headers='keys', tablefmt="psql")
        total = sum(x['count'] for x in records)
        await ctx.send(f"{total} socket events recorded.```\n{table}```")

    async def put_guild_info(self, embed: discord.Embed, guild: Union[PartialGuild, discord.Guild]) -> None:
        embed.add_field(name='Guild Name', value=guild.name)
        embed.add_field(name='Guild ID', value=guild.id)

        if hasattr(guild, 'members'):
            bots = sum(member.bot for member in guild.members)
            humans = guild.member_count - bots
            embed.add_field(name='Member Count', value=f"Bots: {bots}\nHumans: {humans}\nTotal: {len(guild.members)}")

        owner = getattr(guild, 'owner', guild.owner_id)
        embed.add_field(name='Owner', value=base_user_format(owner), inline=False)

        if not hasattr(self, "guild_stats_bulker"):
            self.guild_stats_bulker = WebhookEmbedEmitter(self.bot.config['logging']['guild_alerts'],
                                                          session=self.bot.aiosession, loop=self.bot.loop)
            self.guild_stats_bulker.start()

        await self.guild_stats_bulker.put(embed)

    @LightningCog.listener()
    async def on_lightning_guild_add(self, guild: Union[PartialGuild, discord.Guild]):
        embed = discord.Embed(title="Joined New Guild", color=discord.Color.blue())
        log.info(f"Joined Guild | {guild.name} | {guild.id}")
        await self.put_guild_info(embed, guild)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]):
        embed = discord.Embed(title="Left Guild", color=discord.Color.red())
        log.info(f"Left Guild | {guild.name} | {guild.id}")
        await self.put_guild_info(embed, guild)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Stats(bot))
