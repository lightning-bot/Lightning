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

import asyncio
import io
import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Optional, Tuple, Union

import discord
import psutil
import tabulate
from discord.ext import commands, tasks

from lightning import (CommandLevel, GuildContext, LightningCog,
                       LightningContext, command, group, hybrid_command)
from lightning.converters import InbetweenNumber
from lightning.utils.checks import has_guild_permissions
from lightning.utils.emitters import WebhookEmbedEmitter
from lightning.utils.modlogformats import base_user_format
from lightning.utils.time import natural_timedelta

if TYPE_CHECKING:
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

        self.number_places: Tuple[str, ...] = (
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

        self.process = psutil.Process()

    def cog_unload(self) -> None:
        self.bulk_command_insertion.stop()

        if hasattr(self, 'guild_stats_bulker'):
            self.guild_stats_bulker.close()

    async def insert_command(self, ctx: LightningContext) -> None:
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
                'application_command': True if ctx.interaction else False,
            })

    async def bulk_database_insert(self) -> None:
        if self._command_inserts:
            query = """INSERT INTO command_stats (guild_id, channel_id, user_id, used_at, command_name, failure,
                                                  application_command)
                       SELECT data.guild_id, data.channel_id, data.user_id, data.used_at, data.command_name,
                              data.failure, data.application_command
                       FROM jsonb_to_recordset($1::jsonb) AS
                       data(guild_id BIGINT, channel_id BIGINT, user_id BIGINT, used_at TIMESTAMP,
                            command_name TEXT, failure BOOLEAN, application_command BOOLEAN)
                """
            await self.bot.pool.execute(query, self._command_inserts)
            total = len(self._command_inserts)
            if total > 1:
                log.info(f'{total} commands were added to the database.')
            self._command_inserts.clear()

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

    @LightningCog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.application_command:
            return

        if interaction.command is not None and isinstance(interaction.command, commands.hybrid.HybridAppCommand):
            return

        if interaction.guild is None:
            guild_id = None
        else:
            guild_id = interaction.guild.id
        async with self._lock:
            self._command_inserts.append({
                'guild_id': guild_id,
                'channel_id': interaction.channel.id,
                'user_id': interaction.user.id,
                'used_at': interaction.created_at.isoformat(),
                'command_name': interaction.command.qualified_name,
                'failure': interaction.command_failed,
                'application_command': True
            })

    def format_stat_description(self, records, *, none_msg: str = "Nothing found yet."):
        x = '\n'.join(f'{self.number_places[index]}: {command_name} ({cmd_uses} times)'
                      for (index, (command_name, cmd_uses)) in enumerate(records))

        if len(x) == 0:
            return none_msg

        return x

    async def commands_stats_guild(self, ctx: GuildContext):
        em = discord.Embed(title="Command Stats", color=0xf74b06)
        query = """SELECT COUNT(*), MIN(used_at)
                   FROM command_stats
                   WHERE guild_id=$1;"""
        res = await self.bot.pool.fetchrow(query, ctx.guild.id)
        em.description = f"{res[0]} commands used so far."
        em.set_footer(text='Tracking command usage since')
        em.timestamp = res[1] or discord.utils.utcnow()
        query = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM command_stats
                   WHERE guild_id=$1
                   GROUP BY command_name
                   ORDER BY "cmd_uses" DESC
                   LIMIT 5;
                """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        em.add_field(name="Top Commands", value=self.format_stat_description(records, none_msg="No commands used yet."))

        query = """SELECT user_id,
                        COUNT(*) as "uses"
                   FROM command_stats
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
                   FROM command_stats
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
                   FROM command_stats
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

    async def command_stats_member(self, ctx: LightningContext, member: discord.Member):
        em = discord.Embed(title=f"Command Stats for {member}", color=0xf74b06)
        query = "SELECT COUNT(*), MIN(used_at) FROM command_stats WHERE guild_id=$1 AND user_id=$2;"
        res = await self.bot.pool.fetchrow(query, ctx.guild.id, member.id)
        em.description = f"{res['count']} commands used so far in {ctx.guild.name}."

        em.set_footer(text='First command usage on')
        em.timestamp = res[1] or discord.utils.utcnow()
        query2 = """SELECT command_name,
                        COUNT(*) as "cmd_uses"
                   FROM command_stats
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
                   FROM command_stats
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

        em.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=em)

    @group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    async def stats(self, ctx: GuildContext, member: Optional[discord.Member] = None):
        """Sends stats about which commands are used often in the guild"""
        async with ctx.typing():
            if member is None:
                await self.commands_stats_guild(ctx)
            else:
                await self.command_stats_member(ctx, member)

    @stats.command(name="auditlog", aliases=['table', 'log'], level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    async def stats_audit_log(self, ctx: GuildContext, limit: InbetweenNumber(1, 500) = 50):
        """Shows command stats for the server through a table."""
        async with ctx.typing():
            query = """SELECT command_name, channel_id, user_id, used_at
                       FROM command_stats
                       WHERE guild_id=$1
                       ORDER BY "used_at" DESC
                       LIMIT $2;
                    """
            records = await self.bot.pool.fetch(query, ctx.guild.id, limit)
            headers = {"command_name": "Command", "channel_id": "Channel ID", "user_id": "Author ID",
                       "used_at": "Timestamp"}
            content = f"Showing {len(records)} most recent entries...\n"
            table = tabulate.tabulate(records, headers=headers, tablefmt="psql", disable_numparse=True)
            content += table
            await ctx.send(content)

    @stats.command(name="all")
    @commands.is_owner()
    async def stats_all(self, ctx: LightningContext):
        """Sends stats on the most popular commands used in the bot"""
        async with ctx.typing():
            query = """SELECT command_name,
                        COUNT (*) as "cmd_uses"
                       FROM command_stats
                       GROUP BY command_name
                       ORDER BY "cmd_uses" DESC
                       LIMIT 10;
                    """
            async with self.bot.pool.acquire() as conn:
                records = await conn.fetch(query)
                total = await conn.fetchval("SELECT COUNT(*) FROM command_stats;")
                query = """SELECT COUNT(*) FROM command_stats
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
                           FROM command_stats
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

    @stats.command()
    @commands.is_owner()
    async def recent(self, ctx: LightningContext, limit: int = 10):
        """Shows recent command invocations"""
        query = """SELECT * FROM command_stats ORDER BY used_at DESC LIMIT $1;"""
        records = await self.bot.pool.fetch(query, limit)
        fmt = tabulate.tabulate(records, headers='keys', tablefmt='psql')
        fp = io.StringIO(fmt)
        fp.seek(0)
        await ctx.send(file=discord.File(fp, filename="recents.txt"))

    async def put_guild_info(self, embed: discord.Embed, guild: Union[PartialGuild, discord.Guild]) -> None:
        embed.add_field(name='Guild Name', value=guild.name)
        embed.add_field(name='Guild ID', value=guild.id)

        if members := getattr(guild, 'members', []):
            bots = sum(member.bot for member in members)
            humans = sum(not member.bot for member in members)
            embed.add_field(name='Member Count', value=f"Bots: {bots}\nHumans: {humans}\nTotal: {len(members)}")

        owner = getattr(guild, 'owner', guild.owner_id)
        embed.add_field(name='Owner', value=base_user_format(owner), inline=False)

        if not hasattr(self, "guild_stats_bulker"):
            self.guild_stats_bulker = WebhookEmbedEmitter(self.bot.config.logging.guild_alerts,
                                                          session=self.bot.aiosession)
            self.guild_stats_bulker.start()

        await self.guild_stats_bulker.put(embed)

    @LightningCog.listener()
    async def on_lightning_guild_add(self, guild: Union[PartialGuild, discord.Guild]):
        embed = discord.Embed(title="Joined New Guild", color=discord.Color.blue())
        log.info(f"Joined Guild | {guild.name} | {guild.id}")
        await self.put_guild_info(embed, guild)
        await self.bot.redis_pool.set(f"lightning:guild-joins:{guild.id}", value=1, ex=timedelta(minutes=15))

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]):
        quick = await self.bot.redis_pool.getdel(f"lightning:guild-joins:{guild.id}")
        if quick:
            embed = discord.Embed(title="\N{RACING CAR} Left Guild", color=discord.Color.orange())
        else:
            embed = discord.Embed(title="Left Guild", color=discord.Color.red())

        log.info(f"Left Guild | {guild.name} | {guild.id}")
        await self.put_guild_info(embed, guild)

    @command()
    async def ping(self, ctx: LightningContext) -> None:
        """Tells you the ping."""
        if ctx.guild:
            shard_id = ctx.guild.shard_id
        else:
            shard_id = 0

        shard_latency = round(self.bot.get_shard(shard_id).latency * 1000)

        before = time.monotonic()
        tmp = await ctx.send('Calculating...')
        after = time.monotonic()
        rtt_ms = round((after - before) * 1000)

        await tmp.edit(content=f"Pong!\nshard {shard_id}: `{shard_latency} ms`\nrtt: `{rtt_ms} ms`")

    async def get_bot_author(self):
        user = self.bot.get_user(376012343777427457)
        return user or await self.bot.fetch_user(376012343777427457)

    @hybrid_command()
    async def about(self, ctx: LightningContext) -> None:
        """Gives information about the bot."""
        embed = discord.Embed(title="Lightning", color=0xf74b06, url=self.bot.config.bot.git_repo)
        owners = [self.bot.get_user(u) for u in self.bot.owners]

        author = await self.get_bot_author()
        embed.set_author(name=str(author), icon_url=author.avatar.with_static_format('png'))

        description = [f"This bot instance is owned by {', '.join(str(o) for o in owners)}"]

        embed.set_thumbnail(url=ctx.me.avatar.url)

        if self.bot.config.bot.description:
            description.append(f"**Description**: {self.bot.config.bot.description}")

        memory = self.process.memory_full_info().uss / 1024**2
        description.append(f"**Process**: {memory:.2f} MiB\n**Commit**: [{self.bot.commit_hash[:8]}]"
                           f"({embed.url}/commit/{self.bot.commit_hash})\n**Uptime**: "
                           f"{natural_timedelta(self.bot.launch_time, accuracy=None, suffix=False)}\n"
                           f"**Servers**: {len(self.bot.guilds):,}\n**Shards**: {len(self.bot.shards)}")

        query = "SELECT COUNT(*) FROM command_stats;"
        total_cmds = await self.bot.pool.fetchval(query)
        description.append(f"{total_cmds:,} commands ran.")

        embed.add_field(name="Links", value="[Support Server]"
                                            f"({self.bot.config.bot.support_server_invite}) | "
                                            "[Website](https://lightning.lightsage.dev) | [Ko-Fi]"
                                            "(https://ko-fi.com/lightsage)",
                                            inline=False)
        embed.set_footer(text=f"Lightning v{self.bot.version} | Made with "
                         f"discord.py {discord.__version__}")

        embed.description = '\n'.join(description)

        await ctx.send(embed=embed)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Stats(bot))
