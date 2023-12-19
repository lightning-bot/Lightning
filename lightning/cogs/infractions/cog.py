"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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

from io import BytesIO
from typing import Annotated, Any, Dict, List, Optional

import discord
import matplotlib
import orjson
from discord import app_commands
from discord.ext import commands
from jishaku.functools import executor_function
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator
from sanctum.exceptions import NotFound

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       hybrid_command, hybrid_group)
from lightning.cogs.infractions.converters import (InfractionConverter,
                                                   InfractionTypeConverter)
from lightning.cogs.infractions.ui import (InfractionPaginator,
                                           InfractionSource,
                                           SingularInfractionSource)
from lightning.converters import TargetMember
from lightning.enums import ActionType
from lightning.errors import LightningCommandError
from lightning.events import InfractionDeleteEvent, InfractionUpdateEvent
from lightning.models import InfractionRecord
from lightning.utils.checks import is_server_manager
from lightning.utils.helpers import ticker
from lightning.utils.modlogformats import base_user_format
from lightning.utils.time import add_tzinfo

matplotlib.use('Agg')


class Infractions(LightningCog, required=['Moderation']):
    """Infraction related commands"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.inf_list_contextmenu = app_commands.ContextMenu(name="View Infractions", callback=self.infraction_list)
        bot.tree.add_command(self.inf_list_contextmenu)

        self.numbers = (
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

    async def cog_check(self, ctx) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @hybrid_command(name="mywarns", level=CommandLevel.User)
    @app_commands.guild_only()
    async def my_warns(self, ctx: GuildContext):
        """Shows your warnings in this server"""
        try:
            # type: ignore
            records: List[Dict[str, Any]] = await self.bot.api.get_user_infractions(ctx.guild.id, ctx.author.id)
        except NotFound:
            await ctx.send("No warnings found! Good for you!", ephemeral=True)
            return

        for record in records:
            if record['action'] != 1:
                records.remove(record)

        menu = InfractionPaginator(SingularInfractionSource(records), ctx, timeout=60.0)
        await menu.start(wait=False, ephemeral=True)

    # Context menu
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    async def infraction_list(self, interaction: discord.Interaction, member: discord.Member):
        try:
            records = await self.bot.api.get_user_infractions(interaction.guild.id, member.id)
        except NotFound:
            await interaction.response.send_message(f"No infractions found for {member.mention}!", ephemeral=True)
            return

        ctx = await GuildContext.from_interaction(interaction)
        menu = InfractionPaginator(InfractionSource(records, member=member), ctx, timeout=60.0)
        await menu.start(wait=False, ephemeral=True)

    @hybrid_group(aliases=['inf'], invoke_without_command=True, level=CommandLevel.Mod)
    @app_commands.guild_only()
    @is_server_manager()
    async def infraction(self, ctx: GuildContext) -> None:
        """Commands to manage the server's infractions"""
        await ctx.send_help("infraction")

    @infraction.command(level=CommandLevel.Mod)
    @is_server_manager()
    async def view(self, ctx: GuildContext, infraction: Annotated[InfractionRecord, InfractionConverter]) -> None:
        """Views an infraction"""
        embed = discord.Embed(title=str(infraction.action).capitalize(),
                              description=infraction.reason or "No reason provided",
                              timestamp=add_tzinfo(infraction.created_at))
        embed.add_field(name="User", value=base_user_format(infraction.user))
        embed.add_field(name="Moderator", value=base_user_format(infraction.moderator))
        embed.add_field(name="Active", value=ticker(infraction.active), inline=False)
        embed.set_footer(text="Infraction created at")
        await ctx.send(embed=embed)

    def dispatch_edit_event(self, before: InfractionRecord, after: InfractionRecord):
        self.bot.dispatch("lightning_infraction_update", InfractionUpdateEvent(before, after))

    @infraction.command(level=CommandLevel.Mod)
    @is_server_manager()
    @app_commands.describe(infraction="The infraction's ID")
    async def claim(self, ctx: GuildContext, infraction: Annotated[InfractionRecord, InfractionConverter]) -> None:
        """Claims responsibility for an infraction"""
        try:
            after = await self.bot.api.edit_infraction(ctx.guild.id, infraction.id, {"moderator_id": ctx.author.id})
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction.id} does not exist.")
            return

        await ctx.send(f"Claimed {infraction.id}")
        self.dispatch_edit_event(infraction, InfractionRecord(self.bot, after))

    @infraction.command(level=CommandLevel.Mod)
    @is_server_manager()
    @app_commands.describe(infraction="The infraction's ID", reason="The new reason for the infraction")
    async def edit(self, ctx: GuildContext,
                   infraction: Annotated[InfractionRecord, InfractionConverter],
                   *, reason: str) -> None:
        """Edits the reason for an infraction by its ID"""
        try:
            after = await self.bot.api.edit_infraction(ctx.guild.id, infraction.id,
                                                       {"moderator_id": ctx.author.id, "reason": reason})
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction.id} does not exist.")
            return

        await ctx.send(f"Edited {infraction.id}")
        self.dispatch_edit_event(infraction, InfractionRecord(self.bot, after))

    @infraction.command(level=CommandLevel.Admin)
    @is_server_manager()
    async def transfer(self, ctx: GuildContext, old_user: TargetMember, new_user: TargetMember) -> None:
        """Transfers a user's infractions to another user"""
        confirm = await ctx.confirm(f"Are you sure you want to transfer infractions from {old_user} to {new_user}?")
        if not confirm:
            return

        query = """UPDATE infractions SET user_id=$1 WHERE guild_id=$2 AND user_id=$3;"""
        resp = await self.bot.pool.execute(query, new_user.id, ctx.guild.id, old_user.id)
        resp = resp.split()

        await ctx.send(f"Transferred {resp[-1]} infractions to {new_user.mention}")

    @infraction.command(level=CommandLevel.Mod)
    @is_server_manager()
    async def pardon(self, ctx: GuildContext, infraction_id: int):
        """
        Pardons an infraction

        This sets an infraction's active status to false.
        """
        query = "UPDATE infractions SET active='f' WHERE id=$1 AND guild_id=$2;"
        resp = await self.bot.pool.execute(query, infraction_id, ctx.guild.id)
        if resp == "UPDATE 0":
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.reply(f"Pardoned {infraction_id}")

    @infraction.command(aliases=['remove'], level=CommandLevel.Admin)
    @is_server_manager()
    @app_commands.describe(infraction="The infraction's ID")
    async def delete(self, ctx: GuildContext, infraction: Annotated[InfractionRecord, InfractionConverter]) -> None:
        """Deletes an infraction"""
        confirmation = await ctx.confirm(f"Are you sure you want to delete {infraction.id}? "
                                         "**This infraction cannot be restored once deleted!**")
        if not confirmation:
            return

        # I guess there could be instances where two people are running the same command...
        try:
            await self.bot.api.delete_infraction(ctx.guild.id, infraction.id)
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction.id} does not exist.")
            return

        await ctx.reply("Infraction deleted!")
        self.bot.dispatch("lightning_infraction_delete",
                          InfractionDeleteEvent(infraction, ctx.author))

    @infraction.command(level=CommandLevel.Admin)
    @is_server_manager()
    @commands.bot_has_permissions(attach_files=True)
    async def export(self, ctx: GuildContext) -> None:
        """Exports the server's infractions to a JSON"""
        records = await self.bot.api.get_infractions(ctx.guild.id)

        raw_bytes = BytesIO(orjson.dumps(records))
        raw_bytes.seek(0)
        await ctx.send(file=discord.File(raw_bytes, filename="infractions.json"))

    async def start_infraction_pages(self, ctx: GuildContext, source: InfractionSource) -> None:
        menu = InfractionPaginator(source, ctx, timeout=60.0)
        await menu.start(wait=False)

    async def wrap_request(self, coro):
        try:
            return await coro
        except NotFound:
            raise LightningCommandError("Couldn't find any infractions matching your criteria!")

    @infraction.command(name='list', level=CommandLevel.Mod)
    @is_server_manager()
    @app_commands.describe(member="The member to look up infractions for",
                           action="The action to filter infractions for")
    @app_commands.choices(action=[app_commands.Choice(name=x.capitalize(),
                                                      value=x) for x, _ in ActionType])
    async def list_infractions(self, ctx: GuildContext, member: Optional[discord.User],
                               action: Annotated[Optional[int], InfractionTypeConverter] = None) -> None:
        """Lists infractions that were done in the server with optional filter(s)"""
        if member:
            infs = await self.wrap_request(self.bot.api.get_user_infractions(ctx.guild.id, member.id,
                                                                             action_num=action))
            src = InfractionSource(infs, member=member)
        else:
            infs = await self.wrap_request(self.bot.api.get_infractions(ctx.guild.id, action_num=action))
            src = InfractionSource(infs)

        await self.start_infraction_pages(ctx, src)

    @LightningCog.listener('on_lightning_timemute_complete')
    @LightningCog.listener('on_lightning_timeban_complete')
    @LightningCog.listener('on_lightning_timeout_complete')
    async def deactivate_infractions_on_timer_completion(self, timer):
        query = "UPDATE infractions SET active='f' WHERE extra -> 'timer' = $1;"
        await self.bot.pool.execute(query, timer.id)

    async def detailed_moderator_stats(self, ctx: GuildContext, moderator: discord.Member):
        embed = discord.Embed(title="Detailed Infraction Stats")
        query = """SELECT COUNT (*) as "infractions"
                    FROM infractions
                    WHERE guild_id = $1
                    AND moderator_id = $2;
                    """
        total_count = await self.bot.pool.fetchval(query, ctx.guild.id, moderator.id)
        if not total_count:
            embed.description = f"{moderator.mention} hasn't done any moderation actions yet!"
            return embed

        desc = []

        query = """SELECT moderator_id, COUNT(*) as "count"
                   FROM infractions
                   WHERE guild_id=$1
                   GROUP BY moderator_id
                   ORDER BY "count" DESC
                   LIMIT 1;"""
        record = await self.bot.pool.fetchrow(query, ctx.guild.id)

        if record['moderator_id'] == moderator.id:
            desc.append(f"{moderator.mention} is currently in 1st place for creating the most infractions!"
                        f" ({record['count']})")
        else:
            desc.append(f"{moderator.mention} needs {total_count - record['count']} more infractions to be in 1st place"
                        "!")

        query = """SELECT COUNT(*) as "count"
                   FROM infractions
                   WHERE guild_id=$1
                   AND moderator_id=$2
                   AND created_at > (timezone('UTC', now()) - INTERVAL '7 days');"""
        record = await self.bot.pool.fetchval(query, ctx.guild.id, moderator.id)
        desc.append(f"In the past seven days, {moderator.mention} has made {record or 0} infractions!")

        embed.description = "\n".join(desc)

        # At some point, we'll have some graphs too :)

        return embed

    @executor_function
    def create_guild_graph(self, data: List[int], labels: List[str], inf_data: Dict[int, int]) -> discord.File:
        fig, ax = plt.subplots(2, figsize=[9, 9])
        ax[0].pie(data, autopct="%1.1f%%")
        ax[0].set_title("Top 10 Moderators")
        ax[0].legend(labels, title="Moderators", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

        for num in ActionType:
            d = inf_data.get(num.value)
            if not d:
                inf_data[num.value] = 0

        inf_data = dict(sorted(inf_data.items()))
        ax[1].bar([str(t).capitalize() for t in ActionType], inf_data.values())
        ax[1].set_title("All-Time Actions Taken")
        ax[1].yaxis.set_major_locator(MaxNLocator(integer=True))

        fp = BytesIO()
        plt.savefig(fp, format='png')
        fp.seek(0)
        return discord.File(fp, 'plot.png')

    @infraction.command(name="stats", level=CommandLevel.Mod)
    @is_server_manager()
    @commands.bot_has_permissions(attach_files=True)
    async def infraction_stats(self, ctx: GuildContext, moderator: Optional[discord.Member]) -> None:
        """Shows some stats about this guild's infractions"""
        if moderator:
            embed = await self.detailed_moderator_stats(ctx, moderator)
            await ctx.send(embed=embed)
            return

        query = """SELECT moderator_id,
                        COUNT (*) as "count"
                    FROM infractions
                    WHERE guild_id = $1
                    GROUP BY moderator_id
                    ORDER BY "count" DESC
                    LIMIT 10;
                    """
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        embed = discord.Embed()
        desc = [
            f"{self.numbers[idx]}: <@{record['moderator_id']}> ({record['count']} infractions)\n"
            for idx, record in enumerate(records)
        ]
        embed.description = "".join(desc)

        labels = []
        for record in records:
            if mod := ctx.guild.get_member(record['moderator_id']) or ctx.bot.get_user(record['moderator_id']):
                labels.append(str(mod))
            else:
                labels.append(f"Unknown user with ID: {record['moderator_id']}")

        query = """SELECT action, COUNT (*) as "count"
                   FROM infractions
                   WHERE guild_id=$1
                   GROUP BY action;"""
        typesc = dict(await self.bot.pool.fetch(query, ctx.guild.id))

        f = await self.create_guild_graph([record['count'] for record in records], labels, typesc)
        embed.set_image(url="attachment://plot.png")
        await ctx.send(embed=embed, file=f)
