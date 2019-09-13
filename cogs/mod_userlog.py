# kirigiri - A discord bot.
# Copyright (C) 2018 - Valentijn "noirscape" V.
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
# In addition, the additional clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version; or


import discord
from discord.ext import commands
from utils.user_log import get_userlog, set_userlog, userlog_event_types
from utils.checks import is_staff_or_has_perms, has_staff_role

# Most commands here taken from robocop-ngs mod.py
# https://github.com/aveao/robocop-ng/blob/master/cogs/mod_user.py
# robocop-ng is MIT licensed


class ModUserLog(commands.Cog):
    """
    Companion to moderation cog.

    These commands were taken from robocop-ngs mod_userlog.py

    robocop-ng's mod.py is under the MIT license and is written by aveao / the ReSwitched team.

    See here for the license: https://github.com/aveao/robocop-ng/blob/master/LICENSE
    """
    def __init__(self, bot):
        self.bot = bot

    async def get_userlog_embed_for_id(self, uid: str, name: str, guild, own: bool = False,
                                       event=""):
        own_note = " <:blobaww:560297547260887071> Good for you!" if own else ""
        wanted_events = ["warns", "bans", "kicks", "mutes"]
        if event:
            wanted_events = [event]
        embed = discord.Embed(color=discord.Color.dark_red())
        embed.set_author(name=f"Userlog for {name}")
        userlog = await get_userlog(self.bot, guild)

        if uid not in userlog:
            embed.description = f"<:blobaww:560297547260887071> There are none!{own_note} (no entry)"
            embed.color = discord.Color.green()
            return embed

        for event_type in wanted_events:
            if event_type in userlog[uid] and userlog[uid][event_type]:
                event_name = userlog_event_types[event_type]
                for idx, event in enumerate(userlog[uid][event_type]):
                    issuer = "" if own else f"Issuer: {event['issuer_name']} " \
                                            f"({event['issuer_id']})\n"
                    embed.add_field(name=f"{event_name} {idx + 1}: "
                                         f"{event['timestamp']}",
                                    value=issuer + f"Reason: {event['reason']}",
                                    inline=False)

        if not own and "watch" in userlog[uid]:
            watch_state = "" if userlog[uid]["watch"] else "NOT "
            embed.set_footer(text=f"User is {watch_state}under watch.")

        if not embed.fields:
            embed.description = f"<:blobaww:560297547260887071> There are none!{own_note}"
            embed.color = discord.Color.green()
        return embed

    async def clear_event_from_id(self, uid: str, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            return f"<@{uid}> has no {event_type}!"
        event_count = len(userlog[uid][event_type])
        if not event_count:
            return f"<@{uid}> has no {event_type}!"
        userlog[uid][event_type] = []
        await set_userlog(self.bot, guild, userlog)
        return f"<@{uid}> no longer has any {event_type}!"

    async def delete_event_from_id(self, uid: str, idx: int, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            return f"<@{uid}> has no {event_type}!"
        event_count = len(userlog[uid][event_type])
        if not event_count:
            return f"<@{uid}> has no {event_type}!"
        if idx > event_count:
            return "Index is higher than " \
                   f"count ({event_count})!"
        if idx < 1:
            return "Index is below 1!"
        event = userlog[uid][event_type][idx - 1]
        event_name = userlog_event_types[event_type]
        embed = discord.Embed(color=discord.Color.dark_red(),
                              title=f"{event_name} {idx} on "
                                    f"{event['timestamp']}",
                              description=f"Issuer: {event['issuer_name']}\n"
                                          f"Reason: {event['reason']}")
        del userlog[uid][event_type][idx - 1]
        await set_userlog(self.bot, guild, userlog)
        return embed

    @commands.guild_only()
    @has_staff_role("Helper")
    @commands.command(aliases=["events", "listmodevents", "listevents"])
    async def eventtypes(self, ctx):
        """Lists the available event types, staff only."""
        event_list = [f"{et} ({userlog_event_types[et]})" for et in
                      userlog_event_types]
        events = "\n - ".join(event_list)
        await ctx.send("Available events:\n``` - "
                       f"{events}"
                       "```")

    @commands.guild_only()
    @has_staff_role("Helper")
    @commands.command(name="userlog",
                      aliases=["listwarns", "getuserlog", "listuserlog"])
    async def userlog_cmd(self, ctx, target: discord.Member, event=""):
        """Lists the userlog events for a user, staff only."""
        embed = await self.get_userlog_embed_for_id(str(target.id), str(target),
                                                    event=event, guild=ctx.guild)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @has_staff_role("Helper")
    @commands.command(aliases=["listnotes", "usernotes"])
    async def notes(self, ctx, target: discord.Member):
        """Lists the notes for a user, staff only."""
        embed = await self.get_userlog_embed_for_id(str(target.id), str(target),
                                                    event="notes", guild=ctx.guild)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(aliases=["mywarns"])
    async def myuserlog(self, ctx):
        """Lists your userlog events (warns etc)."""
        embed = await self.get_userlog_embed_for_id(str(ctx.author.id),
                                                    str(ctx.author),
                                                    own=True,
                                                    guild=ctx.guild)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @has_staff_role("Helper")
    @commands.command(aliases=["listwarnsid"])
    async def userlogid(self, ctx, target: int):
        """Lists the userlog events for a user by ID, staff only."""
        embed = await self.get_userlog_embed_for_id(str(target), str(target), guild=ctx.guild)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command(aliases=["clearwarns"])
    async def clearevent(self, ctx, target: discord.Member,
                         event="warns"):
        """Clears all events of given type for a user, Admins only."""
        msg = await self.clear_event_from_id(str(target.id), event, guild=ctx.guild)
        await ctx.send(msg)
        mod = self.bot.get_cog('Mod')
        if not mod:
            return
        else:
            safe_name = await commands.clean_content().convert(ctx, str(target))
            msg = f"🗑 **Cleared {event}**: {ctx.author.mention} cleared" \
                  f" all {event} events of {target.mention} | " \
                  f"{safe_name}"
            await mod.log_send(ctx, msg)

    @commands.guild_only()
    @has_staff_role("Admin")
    @commands.command(aliases=["clearwarnsid"])
    async def cleareventid(self, ctx, target: int, event="warns"):
        """Clears all events of given type for a userid, Admins only."""
        msg = await self.clear_event_from_id(str(target), event, guild=ctx.guild)
        await ctx.send(msg)
        mod = self.bot.get_cog('Mod')
        if not mod:
            return
        else:
            msg = f"🗑 **Cleared {event}**: {ctx.author.mention} cleared" \
                  f" all {event} events of <@{target}> "
            await mod.log_send(ctx, msg)

    @commands.guild_only()
    @has_staff_role("Admin")
    @commands.command(aliases=["delwarn"])
    async def delevent(self, ctx, target: discord.Member, idx: int,
                       event="warns"):
        """Removes a specific event from a user, Admins only."""
        del_event = await self.delete_event_from_id(str(target.id),
                                                    idx, event,
                                                    guild=ctx.guild)
        event_name = userlog_event_types[event].lower()
        # This is hell.
        if isinstance(del_event, discord.Embed):
            await ctx.send(f"{target.mention} has a {event_name} removed!")
            mod = self.bot.get_cog('Mod')
            if not mod:
                return
            else:
                safe_name = await commands.clean_content().convert(ctx, str(target))
                msg = f"🗑 **Deleted {event_name}**: " \
                      f"{ctx.author.mention} removed " \
                      f"{event_name} {idx} from {target.mention} | " \
                      f"{safe_name}"
                await mod.log_send(ctx, msg)
        else:
            await ctx.send(del_event)

    @commands.guild_only()
    @has_staff_role("Admin")
    @commands.command(aliases=["delwarnid"])
    async def deleventid(self, ctx, target: int, idx: int, event="warns"):
        """Removes a specific event from a userid, Admins only."""
        del_event = await self.delete_event_from_id(str(target),
                                                    idx, event,
                                                    guild=ctx.guild)
        event_name = userlog_event_types[event].lower()
        # This is hell.
        if isinstance(del_event, discord.Embed):
            await ctx.send(f"<@{target}> has a {event_name} removed!")
            mod = self.bot.get_cog('Mod')
            if not mod:
                return
            else:
                msg = f"🗑 **Deleted {event_name}**: " \
                      f"{ctx.author.mention} removed " \
                      f"{event_name} {idx} from <@{target}> "
                await mod.log_send(ctx, msg)
        else:
            await ctx.send(del_event)


def setup(bot):
    bot.add_cog(ModUserLog(bot))
