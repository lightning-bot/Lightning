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
from discord.ext.commands import Cog
import datetime
import re
import resources.botemojis as em
import json


class Logger(Cog):
    """Logs user actions"""
    def __init__(self, bot):
        self.bot = bot
        self.check_inv = re.compile(r"((discord\.gg|discordapp\.com/"  # Check Invite
                                    r"+invite)/+[a-zA-Z0-9-]+)",
                                    re.IGNORECASE)

    async def guild_config_id(self, guild_id: int):
        """Async Function to use a provided guild ID instead of relying
        on context (ctx)."""
        query = """SELECT * FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            ret = await con.fetchrow(query, guild_id)
        if ret:
            guild_config = json.loads(ret['log_channels'])
        else:
            guild_config = {}

        return guild_config

    async def invite_filter(self, message):
        if message.author.bot:
            return

        invites = self.check_inv.findall(message.content)
        for invite in invites:
            config = await self.guild_config_id(message.guild.id)
            if "invite_watch" in config:
                msg = f"📨 **Invite Posted** | Jump to message: {message.jump_url}"\
                      f"\nMessage contained invite link: https://{invite[0]}"
                try:
                    await self.bot.get_channel(config["invite_watch"]).send(msg)
                except Exception:
                    pass

    @Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        try:
            query = """SELECT role_id
                    FROM user_restrictions
                    WHERE user_id=$1
                    AND guild_id=$2;
                    """
            rsts = await self.bot.db.fetch(query, member.id, member.guild.id)
            tmp = []
            for r in rsts:
                tmp.append(r[0])
            roles = [discord.utils.get(member.guild.roles, id=rst) for rst in tmp]
            await member.add_roles(*roles, reason="Reapply Role Restrictions")
        except Exception as e:
            self.bot.log.error(e)
            pass
        config = await self.guild_config_id(member.guild.id)
        if "join_log_embed_channel" in config:
            embed = discord.Embed(title=f"{em.member_join} Member Join",
                                  timestamp=datetime.datetime.utcnow(), color=discord.Color.green())
            embed.description = f"{member.mention} | {member}\n🕓 __Account Creation__: "\
                                f"{member.created_at}\n🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config["join_log_embed_channel"]).send(embed=embed)
            except Exception:
                pass
        if "join_log_channel" in config:
            msg = f"{em.member_join}"\
                  f" **Member Join**: {member.mention} | "\
                  f"{member}\n"\
                  f"🕓 __Account Creation__: {member.created_at}\n"\
                  f"🗓 Join Date: {member.joined_at}\n"\
                  f"🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config["join_log_channel"]).send(msg)
            except Exception:
                pass

    @Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()
        config = await self.guild_config_id(member.guild.id)
        if "join_log_embed_channel" in config:
            embed = discord.Embed(title=f"{em.member_leave} Member Leave",
                                  timestamp=datetime.datetime.utcnow(), color=discord.Color.red())
            embed.description = f"{member.mention} | {member}\n🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config["join_log_embed_channel"]).send(embed=embed)
            except Exception:
                pass
        if "join_log_channel" in config:
            msg = f"{em.member_leave} "\
                  f"**Member Leave**: {member.mention} | "\
                  f"{member}\n"\
                  f"📅 Left Date: {datetime.datetime.utcnow()}\n"\
                  f"🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config["join_log_channel"]).send(msg)
            except Exception:
                pass

    @Cog.listener()
    async def on_guild_ban(self, guild, user):
        config = await self.guild_config_id(guild.id)
        if "ban_channel" in config:
            message = f"🔨 **Ban**: {user.mention} | {user}\n"\
                      f"🏷 __User ID__: {user.id}"
            try:
                await self.bot.get_channel(config["ban_channel"]).send(message)
            except Exception:
                pass

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.bot.wait_until_ready()
        config = await self.guild_config_id(guild.id)
        if "ban_channel" in config:
            message = f"⚠ **Unban**: {user.mention} | {user}\n"\
                      f"🏷 __User ID__: {user.id}"
            try:
                await self.bot.get_channel(config["ban_channel"]).send(message)
            except Exception:
                pass

    @Cog.listener()
    async def on_message_delete(self, message):
        await self.bot.wait_until_ready()
        if message.author.bot:  # Does not log bots
            return
        config = await self.guild_config_id(message.guild.id)
        if "message_log_channel" in config:
            msg = "🗑️ **Message deleted**: \n"\
                  f"Author: {self.bot.escape_message(message.author.name)} "\
                  f"(ID: {message.author.id})\nChannel: {message.channel.mention}\n"
            embed = discord.Embed(description=f"Message: {message.clean_content}")
            if message.attachments:
                attachment_urls = []
                for attachment in message.attachments:
                    attachment_urls.append(f'File Name: {attachment.filename} <{attachment.url}>')
                attachment_msg = '\N{BULLET} ' + '\n\N{BULLET} '.join(attachment_urls)
                msg += "\n🔗 **Attachments:** \n"\
                       f"{attachment_msg}"
            # If resulting message is too long, upload to hastebin.
            if len(msg) > 1995:
                haste_url = await self.bot.haste(msg)
                msg = f"🗑️ **Message deleted**: \nMessage was too long. See the link: <{haste_url}>"
            try:
                await self.bot.get_channel(config["message_log_channel"]).send(msg, embed=embed)
            except Exception:
                pass

    @Cog.listener()
    async def on_message_edit(self, before, after):
        await self.bot.wait_until_ready()
        if before.guild is None:
            return
        if before.clean_content == after.clean_content:
            return
        if before.author.bot:  # Don't log bots
            return
        await self.invite_filter(after)  # Check if message has invite
        config = await self.guild_config_id(before.guild.id)
        if "message_log_channel" in config:
            msg = "📝 **Message edit**: \n"\
                  f"Author: {self.bot.escape_message(after.author.name)} "\
                  f"(ID: {after.author.id})\nChannel: {after.channel.mention}\n"
            embed = discord.Embed(description=f"Before: {before.clean_content}\nAfter: {after.clean_content}")
            # if after.attachments:
            #    attachment_urls = []
            #    for attachment in after.attachments:
            #        attachment_urls.append(f'File Name: {attachment.filename} <{attachment.url}>')
            #    attachment_msg = '\N{BULLET} ' + '\n\N{BULLET} '.join(attachment_urls)
            #    msg += "🔗 **Attachments:** \n"\
            #           f"{attachment_msg}"
            # If resulting message is too long, upload to hastebin.
            if len(msg) > 1985:
                hastemsg = "📝 **Message edit**: \n"\
                           f"Author: {self.bot.escape_message(after.author.name)}\n"\
                           f"(ID: {after.author.id})\nChannel: {after.channel.mention}\n"\
                           f"Before: {before.clean_content}\n\nAfter: {after.clean_content}"
                haste_url = await self.bot.haste(hastemsg)
                msg = f"📝 **Message Edited**: \nMessage was too long. See the link: <{haste_url}>"
            try:
                await self.bot.get_channel(config["message_log_channel"]).send(msg, embed=embed)
            except Exception:
                pass

    @Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()
        await self.invite_filter(message)  # Check if message has invite

    @Cog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        config = await self.guild_config_id(before.guild.id)
        if "event_embed_channel" in config:
            if before.roles == after.roles:
                return
            added_roles = [role.name for role in after.roles if role not in before.roles]
            removed_roles = [role.name for role in before.roles if role not in after.roles]
            embed = discord.Embed(title="Member Update", color=discord.Color.blurple(),
                                  timestamp=datetime.datetime.utcnow())
            embed.set_author(name=str(after), icon_url=str(after.avatar_url))
            if len(added_roles) != 0:
                embed.add_field(name="Added Role", value=", ".join(added_roles))
            if len(removed_roles) != 0:
                embed.add_field(name="Removed Role", value=", ".join(removed_roles))
            try:
                await self.bot.get_channel(config["event_embed_channel"]).send(embed=embed)
            except:
                pass
        if "event_channel" in config:
            msg = ""
            if before.roles != after.roles:  # Taken from robocop-ng. MIT Licensed.
                # role removal
                role_removal = []
                for index, role in enumerate(before.roles):
                    if role not in after.roles:
                        role_removal.append(role)
                    # role addition
                role_addition = []
                for index, role in enumerate(after.roles):
                    if role not in before.roles:
                        role_addition.append(role)

                if len(role_addition) != 0 or len(role_removal) != 0:
                    msg += "\n👑 __Role change__: "
                    roles = []
                    for role in role_removal:
                        roles.append("_~~" + role.name + "~~_")
                    for role in role_addition:
                        roles.append("__**" + role.name + "**__")
                    for index, role in enumerate(after.roles):
                        if role.name == "@everyone":
                            continue
                        if role not in role_removal and role not in role_addition:
                            roles.append(role.name)
                msg += ", ".join(roles)
            if msg:  # Ending
                msg = f"ℹ️ **Member update**: {self.bot.escape_message(after)} | "\
                      f"{after.id} {msg}"
            try:
                await self.bot.get_channel(config["event_channel"]).send(msg)
            except Exception:
                pass


def setup(bot):
    bot.add_cog(Logger(bot))
