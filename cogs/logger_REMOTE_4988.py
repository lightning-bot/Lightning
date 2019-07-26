import discord
from discord.ext.commands import Cog
import db.per_guild_config
import datetime
import re
from humanize import naturaldate
from utils.restrictions import get_user_restrictions
from utils.guild_config import read_guild_config

class Logger(Cog):
    """Logs user actions"""
    def __init__(self, bot):
        self.bot = bot
        self.check_inv = re.compile(r"((discord\.gg|discordapp\.com/" # Check Invite
                                    r"+invite)/+[a-zA-Z0-9-]+)",
                                    re.IGNORECASE)
        self.bot.log.info(f'{self.qualified_name} loaded')

    async def invite_filter(self, message):
        if message.author.bot:
            return
        
        invites = self.check_inv.findall(message.content)
        for invite in invites:
            # Define a temp var
            config = read_guild_config(message.guild.id, "invite_watch_chan")
            if config is not False:
                msg = f"📨 **Invite Posted** | Jump to message: {message.jump_url}"\
                      f"\nMessage contained invite link: https://{invite[0]}"
                try:
                    await self.bot.get_channel(config).send(msg)
                except:
                    pass

    @Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        try:
            rsts = get_user_restrictions(member.guild, member.id)
            roles = [discord.utils.get(member.guild.roles, id=rst) for rst in rsts]
            await member.add_roles(*roles)
        except:
            pass
        config = read_guild_config(member.guild.id, "join_log_embed_channel")
        if config is not False:
            embed = discord.Embed(title="<:join:575348114802606080> Member Join", timestamp=datetime.datetime.utcnow(), color=discord.Color.green())
            embed.description = f"{member.mention} | {member}\n🕓 __Account Creation__: {member.created_at}\n🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config).send(embed=embed)
            except:
                pass
        config2 = read_guild_config(member.guild.id, "join_log_channel")
        if config2 is not False:
            msg = f"<:join:575348114802606080> **Member Join**: {member.mention} | "\
                  f"{member}\n"\
                  f"🕓 __Account Creation__: {member.created_at}\n"\
                  f"🗓 Join Date: {member.joined_at}\n"\
                  f"🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config2).send(msg)
            except:
                pass

    @Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()
        config = read_guild_config(member.guild.id, "join_log_embed_channel")
        if config is not False:
            embed = discord.Embed(title="<:leave:575348321401569312> Member Leave", 
                                  timestamp=datetime.datetime.utcnow(), 
                                  color=discord.Color.red())
            embed.description = f"{member.mention} | {member}\n🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config).send(embed=embed)
            except:
                pass
        config2 = read_guild_config(member.guild.id, "join_log_channel")
        if config2 is not False:
            msg = f"<:leave:575348321401569312> **Member Leave**: {member.mention} | "\
                  f"{member}\n"\
                  f"📅 Left Date: {datetime.datetime.utcnow()}\n"\
                  f"🏷 __User ID__: {member.id}"
            try:
                await self.bot.get_channel(config2).send(msg)
            except:
                pass

    @Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.bot.wait_until_ready()
        config = read_guild_config(guild.id, "ban_log_channel")
        if config is not False:
            message = f"🔨 **Ban**: {user.mention} | {user}\n"\
                      f"🏷 __User ID__: {user.id}"
            try:
                await self.bot.get_channel(config).send(message)
            except:
                pass

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.bot.wait_until_ready()
        config = read_guild_config(guild.id, "ban_log_channel")
        if config is not False:
            message = f"⚠ **Unban**: {user.mention} | {user}\n"\
                      f"🏷 __User ID__: {user.id}"
            try:
                await self.bot.get_channel(config).send(message)
            except:
                pass

    @Cog.listener()
    async def on_message_delete(self, message):
        await self.bot.wait_until_ready()
        if message.author.bot: # Does not log bots
            return
        config = read_guild_config(message.guild.id, "message_log_channel")
        if config is not False:
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
                # If resulting message is too long, upload to hastebin. Taken from robocop-ng which is under the MIT License.
            if len(message.clean_content) > 2000:
                haste_url = await self.bot.haste(msg)
                msg = f"🗑️ **Message deleted**: \nMessage was too long. See the link: <{haste_url}>"
            try:
                await self.bot.get_channel(config).send(msg, embed=embed)
            except:
                pass

    @Cog.listener()
    async def on_message_edit(self, before, after):
        await self.bot.wait_until_ready()
        if before.guild is None:
            return
        if before.clean_content == after.clean_content:
            return
        if before.author.bot: # Don't log bots
            return
        await self.invite_filter(after) # Check if message has invite
        config = read_guild_config(before.guild.id, "message_log_channel")
        if config is not False:
            msg = "📝 **Message edit**: \n"\
                  f"Author: {self.bot.escape_message(after.author.name)} "\
                  f"(ID: {after.author.id})\nChannel: {after.channel.mention}\n"
            embed = discord.Embed(description=f"Before: {before.clean_content}\nAfter: {after.clean_content}")
                #if after.attachments:
                #    attachment_urls = []
                #    for attachment in after.attachments:
                #        attachment_urls.append(f'File Name: {attachment.filename} <{attachment.url}>')
                #    attachment_msg = '\N{BULLET} ' + '\n\N{BULLET} '.join(attachment_urls)
                #    msg += "🔗 **Attachments:** \n"\
                #           f"{attachment_msg}"
                # If resulting message is too long, upload to hastebin.  
                # Idea Taken from robocop-ng.
            if len(after.clean_content) > 2000:
                hastemsg = "📝 **Message edit**: \n"\
                          f"Author: {self.bot.escape_message(after.author.name)} "\
                          f"(ID: {after.author.id})\nChannel: {after.channel.mention}\n"\
                          f"Before: {before.clean_content}\n\nAfter: {after.clean_content}"
                haste_url = await self.bot.haste(hastemsg)
                msg = f"📝 **Message Edited**: \nMessage was too long. See the link: <{haste_url}>"
            try:
                await self.bot.get_channel(config).send(msg, embed=embed)
            except:
                pass

    @Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()

        await self.invite_filter(message) # Check if message has invite

    @Cog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        config = read_guild_config(after.guild.id, "event_embed_channel")
        if config is not False:
            if before.roles == after.roles:
                return
            added_roles = [role.name for role in after.roles if role not in before.roles]
            removed_roles = [role.name for role in before.roles if role not in after.roles]
            embed = discord.Embed(title="Member Update", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
            embed.set_author(name=str(after), icon_url=str(after.avatar_url))
            if len(added_roles) != 0:
                embed.add_field(name="Added Role", value=", ".join(added_roles))
            if len(removed_roles) != 0:
                embed.add_field(name="Removed Role", value=", ".join(removed_roles))
            try:
                await self.bot.get_channel(config).send(embed=embed)
            except:
                pass
        config2 = read_guild_config(after.guild.id, "event_log_channel")
        if config2 is not False:
            msg = ""
            if before.roles != after.roles: # Taken from robocop-ng. MIT Licensed.
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
            if msg: # Ending
                msg = f"ℹ️ **Member update**: {self.bot.escape_message(after)} | "\
                    f"{after.id} {msg}"
            try:
                await self.bot.get_channel(config2).send(msg)
            except:
                pass

def setup(bot):
    bot.add_cog(Logger(bot))