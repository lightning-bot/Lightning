import discord
from discord.ext.commands import Cog
import db.per_guild_config
import datetime
import re
from humanize import naturaldate
from utils.restrictions import get_user_restrictions

class Logger(Cog):
    """Logs user actions"""
    def __init__(self, bot):
        self.bot = bot
        self.check_inv = re.compile(r"((discord\.gg|discordapp\.com/" # Check Invite
                                    r"+invite)/+[a-zA-Z0-9-]+)",
                                    re.IGNORECASE)
        self.bot.log.info(f'{self.qualified_name} loaded')

    # Snippet of code from Noirscape's kirigiri. Under the AGPL 3.0 License, https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")

    async def invite_filter(self, message):
        if message.author.bot:
            return
        
        invites = self.check_inv.findall(message.content)
        for invite in invites:
            if db.per_guild_config.exist_guild_config(message.guild, "config"):
                config = db.per_guild_config.get_guild_config(message.guild, "config")
                if "invite_watch" in config:
                    msg = f"📨 **Invite Posted** | Jump to message: {message.jump_url}\nMessage contained invite link: https://{invite[0]}"
                    await self.bot.get_channel(config["invite_watch"]).send(msg)


    @Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        rsts = get_user_restrictions(member.guild, member.id)
        roles = [discord.utils.get(member.guild.roles, id=rst) for rst in rsts]
        await member.add_roles(*roles)
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "join_log_embed_channel" in config:
                embed = discord.Embed(title="<:join:575348114802606080> Member Join", timestamp=datetime.datetime.utcnow(), color=discord.Color.green())
                embed.description = f"{member.mention} | {member}\n🕓 __Account Creation__: {member.created_at}\n🏷 __User ID__: {member.id}"
                try:
                    await self.bot.get_channel(config["join_log_embed_channel"]).send(embed=embed)
                except:
                    pass
            if "join_log_channel" in config:
                msg = f"<:join:575348114802606080> **Member Join**: {member.mention} | "\
                 f"{member}\n"\
                 f"🕓 __Account Creation__: {member.created_at}\n"\
                 f"🗓 Join Date: {member.joined_at}\n"\
                 f"🏷 __User ID__: {member.id}"
                try:
                    await self.bot.get_channel(config["join_log_channel"]).send(msg)
                except:
                    pass

    @Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "join_log_embed_channel" in config:
                embed = discord.Embed(title="<:leave:575348321401569312> Member Leave", timestamp=datetime.datetime.utcnow(), color=discord.Color.red())
                embed.description = f"{member.mention} | {member}\n🏷 __User ID__: {member.id}"
                try:
                    await self.bot.get_channel(config["join_log_embed_channel"]).send(embed=embed)
                except:
                    pass
            if "join_log_channel" in config:
                msg = f"<:leave:575348321401569312> **Member Leave**: {member.mention} | "\
                    f"{member}\n"\
                    f"📅 Left Date: {datetime.datetime.utcnow()}\n"\
                    f"🏷 __User ID__: {member.id}"
                try:
                    await self.bot.get_channel(config["join_log_channel"]).send(msg)
                except:
                    pass

    @Cog.listener()
    async def on_guild_ban(self, guild, user):
        if db.per_guild_config.exist_guild_config(guild, "config"):
            config = db.per_guild_config.get_guild_config(guild, "config")
            if "ban_embed_channel" in config:
                embed = discord.Embed(title="Ban", timestamp=datetime.datetime.utcnow(), color=discord.Color.red())
                embed.description = f"{user.mention} | {user}\n🏷 __User ID__: {user.id}"
                try:
                    await self.bot.get_channel(config["ban_embed_channel"]).send(embed=embed)
                except:
                    pass
            if "ban_channel" in config:
                message = f"🔨 **Ban**: {user.mention} | {user}\n"\
                          f"🏷 __User ID__: {user.id}"
                try:
                    await self.bot.get_channel(config["ban_channel"]).send(message)
                except:
                    pass

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(guild, "config"):
            config = db.per_guild_config.get_guild_config(guild, "config")
            if "ban_embed_channel" in config:
                embed = discord.Embed(title="Unban", timestamp=datetime.datetime.utcnow(), color=discord.Color.red())
                embed.description = f"{user.mention} | {user}\n🏷 __User ID__: {user.id}"
                try:
                    await self.bot.get_channel(config["ban_embed_channel"]).send(embed=embed)
                except:
                    pass
            if "ban_channel" in config:
                message = f"⚠ **Unban**: {user.mention} | {user}\n"\
                          f"🏷 __User ID__: {user.id}"
                try:
                    await self.bot.get_channel(config["ban_channel"]).send(message)
                except:
                    pass

    @Cog.listener()
    async def on_message_delete(self, message):
        await self.bot.wait_until_ready()
        if message.author.bot: # Does not log bots
            return
        if db.per_guild_config.exist_guild_config(message.guild, "config"):
            config = db.per_guild_config.get_guild_config(message.guild, "config")
            if "message_log_channel" in config:
                msg = "🗑️ **Message deleted**: \n"\
                      f"Author: {self.bot.escape_message(message.author.name)} "\
                      f"(ID: {message.author.id})\nChannel: {message.channel.mention}\n"\
                      f"```{message.clean_content}```" # Wrap in a code block
                # If resulting message is too long, upload to hastebin. Taken from robocop-ng which is under the MIT License.
                if len(msg) > 2000:
                    haste_url = await self.bot.haste(msg)
                    msg = f"🗑️ **Message deleted**: \nMessage was too long. See the link: <{haste_url}>"
                try:
                    await self.bot.get_channel(config["message_log_channel"]).send(msg)
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
        if db.per_guild_config.exist_guild_config(before.guild, "config"):
            config = db.per_guild_config.get_guild_config(before.guild, "config")
            if "message_log_channel" in config:
                msg = "📝 **Message edit**: \n"\
                      f"Author: {self.bot.escape_message(after.author.name)} "\
                      f"(ID: {after.author.id})\nChannel: {after.channel.mention}\n"\
                      f"Before: ```{before.clean_content}```\nAfter: ```{after.clean_content}```" # Code Block Wrapping
                # If resulting message is too long, upload to hastebin. Taken from robocop-ng which is under the MIT License.
                if len(msg) > 2000:
                    haste_url = await self.bot.haste(msg)
                    msg = f"📝 **Message Edited**: \nMessage was too long. See the link: <{haste_url}>"
                try:
                    await self.bot.get_channel(config["message_log_channel"]).send(msg)
                except:
                    pass

    @Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()

        await self.invite_filter(message) # Check if message has invite

    @Cog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(before.guild, "config"):
            config = db.per_guild_config.get_guild_config(before.guild, "config")
            if "event_embed_channel" in config:
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
                    await self.bot.get_channel(config["event_embed_channel"]).send(embed=embed)
                except:
                    pass
            if "event_channel" in config:
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
                    await self.bot.get_channel(config["event_channel"]).send(msg)
                except:
                    pass





def setup(bot):
    bot.add_cog(Logger(bot))
