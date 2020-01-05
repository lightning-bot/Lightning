# Lightning.py - A multi-purpose Discord bot
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

from discord.ext import commands
import discord
from utils.checks import is_guild, has_staff_role, is_bot_manager_or_staff
from datetime import datetime
import json
import config
from utils.time import natural_timedelta, FutureTime, get_utc_timestamp


class LightningHub(commands.Cog):
    """Helper commands for Lightning Hub only."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @is_guild(527887739178188830)
    @commands.has_any_role("Trusted", "Verified")
    async def sr(self, ctx, *, text: str = ""):
        """Request staff assistance. Trusted and Verified only."""
        staff = self.bot.get_channel(536376192727646208)
        if text:
            # Prevent extra mentions. We'll clean this later.
            embed = discord.Embed(color=discord.Color.red())
            embed.description = text
            embed.add_field(name="Jump!", value=f"{ctx.message.jump_url}")
        await staff.send(f"‼ {ctx.author.mention} needs a staff member. @here", embed=(embed if text != "" else None))
        await ctx.message.add_reaction("✅")
        await ctx.send("Online staff have been notified of your request.", delete_after=50)

    @commands.command()
    @is_guild(527887739178188830)
    @has_staff_role("Helper")
    async def elevate(self, ctx):
        """Gains the elevated role. Use with care!"""
        target = ctx.author
        role = discord.Object(id=527996858908540928)
        await target.add_roles(role, reason=str(ctx.author))
        await ctx.safe_send(f"{target} is now elevated!")

    @commands.command(aliases=['unelevate'])
    @is_guild(527887739178188830)
    @has_staff_role("Helper")
    async def deelevate(self, ctx):
        """Removes the elevated role. Use with care."""
        target = ctx.author
        role = discord.Object(id=527996858908540928)

        await target.remove_roles(role, reason=str(ctx.author))
        await ctx.safe_send(f"{target} is now unelevated!")

    @commands.command()
    @is_guild(527887739178188830)
    @has_staff_role("Helper")
    async def block(self, ctx, member: discord.Member,
                    channels: commands.Greedy[discord.TextChannel] = None,
                    *, reason: str = ""):
        """Blocks a user from a channel or channels"""
        if channels is None:
            raise commands.BadArgument('You must specify channels!')
        for channel in channels:
            await channel.set_permissions(member, read_messages=False,
                                          send_messages=False,
                                          reason=reason)
        chans = ", ".join(x.mention for x in channels)
        await ctx.send(f"Blocked {member.mention} from viewing {chans}")
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(member))
        msg = f"🚫 **Channel Block**: {ctx.author.mention} blocked "\
              f"{member.mention} | {safe_name} from viewing {chans}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future"\
                   f", it is recommended to use "\
                   f"`{ctx.prefix}block {ctx.command.signature}`"
        await mod_log_chan.send(msg)

    @commands.command()
    @is_guild(527887739178188830)
    @commands.is_owner()
    async def rolelock(self, ctx, emoji: discord.Emoji, roles: commands.Greedy[discord.Role] = None):
        if roles is None:
            return await emoji.edit(roles=None)
        role = []
        if roles:
            for r in roles:
                role.append(r)
        realroles = list(emoji.roles)
        realroles.extend(role)
        await emoji.edit(name=emoji.name, roles=realroles)
        await ctx.send(f"Role locked {emoji}")

    @commands.command(usage="<member> <channels...> <duration> [reason]",
                      aliases=['timeblock'])
    @is_guild(527887739178188830)
    @has_staff_role("Helper")
    async def tempblock(self, ctx, member: discord.Member,
                        channels: commands.Greedy[discord.TextChannel],
                        duration: FutureTime, *, reason: str = ""):
        """Temp Blocks a user from a channel or channels"""
        if len(channels) == 0:
            raise commands.BadArgument('You must specify channels!')
        idlist = []
        for channel in channels:
            await channel.set_permissions(member, read_messages=False,
                                          send_messages=False,
                                          reason=reason)
            idlist.append(channel.id)
        chans = ", ".join(x.mention for x in channels)
        duration_text = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt)
        duration_text = f"{timed_txt} ({duration_text})"
        timer = self.bot.get_cog('TasksManagement')
        if not timer:
            return await ctx.send("Sorry, the timer system "
                                  "is currently unavailable.")
        ext = {"guild_id": ctx.guild.id, "user_id": member.id,
               "channels": idlist}
        await timer.add_job("timeblock", datetime.utcnow(),
                            duration.dt, ext)
        await ctx.send(f"Temp blocked {member.mention} from viewing "
                       f"{chans}. It expires in {duration_text}.")
        dm_message = f"You were temporarily blocked on {ctx.guild.name} "\
                     f"from viewing {chans}!"
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += f"\n\nThis block will expire {duration_text}."
        try:
            await member.send(dm_message)
        except discord.errors.Forbidden:
            pass
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(member))
        msg = f"🚫 **Temporary Channel Block**: {ctx.author.mention} blocked "\
              f"{member.mention} | {safe_name} from viewing {chans}"\
              f"\nBlock expires at {duration_text}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future"\
                   f", it is recommended to use "\
                   f"`{ctx.prefix}tempblock {ctx.command.signature}`"
        await mod_log_chan.send(msg)

    @commands.group(invoke_without_command=True)
    @is_guild(527887739178188830)
    async def ticket(self, ctx, *, info: str):
        """Creates a bug ticket. Please provide a detailed description."""
        query = """INSERT INTO bug_tickets (status, ticket_info, created)
                   VALUES ($1, $2, $3)
                   RETURNING id;
                """
        if ctx.message.attachments:
            for message in ctx.message.attachments:
                info += f" {message.url}\n"
        ext = {"text": info, "author_id": ctx.author.id}
        id = await self.bot.db.fetchrow(query, "Received", json.dumps(ext), ctx.message.created_at)
        e = discord.Embed(title=f"Bug Report - ID: {id[0]}", description=info)
        e.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        e.timestamp = datetime.utcnow()
        e.set_footer(text="Status: Received")
        ch = self.bot.get_channel(config.bug_reports_channel)
        msg = await ch.send(embed=e)
        query = """UPDATE bug_tickets
                   SET guild_id=$2, channel_id=$3, message_id=$4
                   WHERE id=$1;
                """
        await self.bot.db.execute(query, id[0], msg.guild.id, msg.channel.id, msg.id)
        await ctx.safe_send(f"Created a bug ticket with ID {id[0]}. "
                            "You can see updates on your ticket by looking in the "
                            f"bug-reports channel or by using `.ticket info {id[0]}`")

    @ticket.command(name="info")
    @is_guild(527887739178188830)
    async def ticket_info(self, ctx, ticket_id: int):
        """Gives you information on a ticket"""
        query = """SELECT guild_id, channel_id, message_id, ticket_info, status, created
                   FROM bug_tickets WHERE id=$1;"""
        res = await self.bot.db.fetchrow(query, ticket_id)
        if res is None:
            return await ctx.send("Invalid Ticket ID!")
        ext = json.loads(res['ticket_info'])
        embed = discord.Embed(title="Ticket Info",
                              description=ext['text'],
                              color=0xf74b06)
        uid = await self.bot.fetch_user(ext['author_id'])
        embed.set_author(name=uid, icon_url=uid.avatar_url)
        embed.timestamp = res['created']
        embed.set_footer(text=f"Status: {res['status']}")
        await ctx.send(embed=embed)

    async def update_ticket_embed(self, id, info, status, color):
        guid = self.bot.get_guild(info['guild_id'])
        cid = guid.get_channel(info['channel_id'])
        mid = await cid.fetch_message(info['message_id'])
        embed = mid.embeds[0].copy()
        embed.color = color
        embed.set_footer(text=f"Status: {status}")
        await mid.edit(embed=embed)

    @ticket.group(aliases=['update'])
    @is_guild(527887739178188830)
    @is_bot_manager_or_staff("Helper")
    async def status(self, ctx):
        """Updates a ticket's status"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @status.command(name="yellow", aliases=['y'])
    @is_guild(527887739178188830)
    @is_bot_manager_or_staff("Helper")
    async def ticket_status_y(self, ctx, ticket_id: int, *, status: str):
        """Updates a ticket's status to a yellow color

        Status should be "Identified"
        """
        query = """SELECT guild_id, channel_id, message_id, ticket_info
                   FROM bug_tickets WHERE id=$1;"""
        res = await self.bot.db.fetchrow(query, ticket_id)
        if res is None:
            return await ctx.send("Couldn't find that id!")
        query = """UPDATE bug_tickets SET status=$1 WHERE id=$2"""
        await self.bot.db.execute(query, status, ticket_id)
        await self.update_ticket_embed(ticket_id, res, status, 0xf1c40f)
        await ctx.send(f"Updated ticket {ticket_id}.")

    @status.command(name="green", aliases=['g'])
    @is_guild(527887739178188830)
    @is_bot_manager_or_staff("Helper")
    async def ticket_status_g(self, ctx, ticket_id: int, *, status: str):
        """Updates a ticket's status to a green color

        Status should be "Resolved"
        """
        query = """SELECT guild_id, channel_id, message_id, ticket_info
                   FROM bug_tickets WHERE id=$1;"""
        res = await self.bot.db.fetchrow(query, ticket_id)
        if res is None:
            return await ctx.send("Couldn't find that id!")
        query = """UPDATE bug_tickets SET status=$1 WHERE id=$2"""
        await self.bot.db.execute(query, status, ticket_id)
        await self.update_ticket_embed(ticket_id, res, status, 0x2ecc71)
        await ctx.send(f"Updated ticket {ticket_id}.")

    @status.command(name="red", aliases=['r'])
    @is_guild(527887739178188830)
    @is_bot_manager_or_staff("Helper")
    async def ticket_status_r(self, ctx, ticket_id: int, *, status: str):
        """Updates a ticket's status to a red color

        Status can be "Investigating" or "Bad Ticket"/"No Info Provided"
        """
        query = """SELECT guild_id, channel_id, message_id, ticket_info
                   FROM bug_tickets WHERE id=$1;"""
        res = await self.bot.db.fetchrow(query, ticket_id)
        if res is None:
            return await ctx.send("Couldn't find that id!")
        query = """UPDATE bug_tickets SET status=$1 WHERE id=$2"""
        await self.bot.db.execute(query, status, ticket_id)
        await self.update_ticket_embed(ticket_id, res, status, 0xe74c3c)
        await ctx.send(f"Updated ticket {ticket_id}.")

    @commands.Cog.listener()
    async def on_timeblock_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        guild = self.bot.get_guild(ext['guild_id'])
        member = guild.get_member(ext['user_id'])
        for channel in ext['channels']:
            try:
                ch = guild.get_channel(channel)
                await ch.set_permissions(member,
                                         overwrite=None,
                                         reason="PowersCron: "
                                         "Auto Unblock")
            except Exception as e:
                self.bot.log.error(e)
                pass


def setup(bot):
    bot.add_cog(LightningHub(bot))
