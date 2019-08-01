import discord
from discord.ext import commands
import db.per_guild_config
from typing import Union
from database import StaffRoles, Roles, Config, AutoRoles
from utils.custom_prefixes import add_prefix, remove_prefix, get_guild_prefixes

class Prefix(commands.Converter):
    # Based off R. Danny's Converter
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
            await ctx.send("That is a reserved prefix already in use.")
            raise commands.BadArgument('That is a reserved prefix already in use.')
        return argument

class Configuration(commands.Cog):
    """Server Configuration Commands"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    # Snippet of Code taken from Noirscape's kirigiri. https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")

    # Snippet of code taken from Noirscape's kirigiri. https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    @commands.group(aliases=['logging'])
    @commands.has_permissions(administrator=True)
    async def log(self, ctx):
        """Setup various compact logging for the server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.has_permissions(administrator=True)
    @log.command(name="join-logs", aliases=['joinlogs'])
    async def setjoinlogs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users join or leave your server and sends it to the specified logging channel. 

        Compact Logs"""
        if channel == "disable":
            ctx.guild_config.pop("join_log_channel")
            await ctx.send("Member join and leave logging disabled.")
        else:
            ctx.guild_config["join_log_channel"] = channel.id
            await ctx.send(f"Member join and leave logging set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.group()
    async def embed(self, ctx):
        """Set up embedded logging.""" # For those who don't like compact logging
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)


    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @embed.command(name="setjoinlogs", aliases=['set-join-logs'])
    async def setjoinlogs_embed(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users join or leave your server and sends it to the specified logging channel. 
        Embedded Logs"""
        if channel == "disable":
            ctx.guild_config.pop("join_log_embed_channel")
            await ctx.send("Embedded member join and leave logging disabled.")
        else:
            ctx.guild_config["join_log_embed_channel"] = channel.id
            await ctx.send(f"Embedded member join and leave logging set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @embed.command(name="set-role-logs", aliases=['setrolelogs'])
    async def set_event_embed_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users change their roles or get theirs changed and sends it to the specified logging channel.
        Embedded Logs"""
        if channel == "disable":
            ctx.guild_config.pop("event_embed_channel")
            await ctx.send("Embedded member role logs have been disabled.")
        else:
            ctx.guild_config["event_embed_channel"] = channel.id
            await ctx.send(f"Embedded member role logs have been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @embed.command(name="set-ban-logs", aliases=['setbanlog', 'setbanlogs'])
    async def set_embed_ban_log(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set server ban log channel. Embedded"""
        if channel == "disable":
            ctx.guild_config.pop("ban_embed_channel")
            await ctx.send("Server ban log channel has been disabled.")
        else:
            ctx.guild_config["ban_embed_channel"] = channel.id
            await ctx.send(f"Server ban log channel has been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.has_permissions(administrator=True)
    @log.command(name="mod-logs", aliases=['modlogs'])
    async def set_mod_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set where moderation actions should be logged"""
        if channel == "disable":
            ctx.guild_config.pop("log_channel")
            await ctx.send("Moderation logs have been disabled.")
        else:
            ctx.guild_config["log_channel"] = channel.id
            await ctx.send(f"Moderation logs have been set to {channel.mention} <:kurisu:561618919937409055>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="role-logs", aliases=['rolelogs'])
    async def set_event_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """If enabled, tracks whenever users change their roles or get theirs changed and sends it to the specified logging channel.
        Compact Logs"""
        if channel == "disable":
            ctx.guild_config.pop("event_channel")
            await ctx.send("Member role logs have been disabled.")
        else:
            ctx.guild_config["event_channel"] = channel.id
            await ctx.send(f"Member role logs have been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name='ban-logs', aliases=['banlogs'])
    async def set_ban_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set server ban log channel."""
        if channel == "disable":
            ctx.guild_config.pop("ban_channel")
            await ctx.send("Server ban log channel has been disabled.")
        else:
            ctx.guild_config["ban_channel"] = channel.id
            await ctx.send(f"Server ban log channel has been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="message-logs", aliases=['messagelogs'])
    async def setmsglogchannel(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the Message Log Channel"""
        if channel == "disable":
            ctx.guild_config.pop("message_log_channel")
            await ctx.send("Message Logging has been disabled")
        else:
            ctx.guild_config["message_log_channel"] = channel.id
            await ctx.send(f"The message log channel has been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @log.command(name="invite-watch", aliases=['invitewatch'])
    async def set_invite_watch(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the Invite Watching Channel"""
        if channel == "disable":
            ctx.guild_config.pop("invite_watch")
            await ctx.send("Invite Watching has been disabled")
        else:
            ctx.guild_config["invite_watch"] = channel.id
            await ctx.send(f"Invite watching will be sent to {channel.mention}. Please note that this doesn't delete invites. <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.command(name="set-mod-role", aliases=['setmodroles', 'set-mod-roles'])
    @commands.has_permissions(administrator=True)
    async def set_mod_role(self, ctx, target: str, level: str):
        """
        Set the various mod roles.
        :param target: Target role to set. Case specific.
        :param level: Any of "Helper", "Moderator" or "Admin".
        """
        role = discord.utils.get(ctx.guild.roles, name=target)
        if not role:
            return await ctx.send(":x: That role does not exist.")

        if level.lower() not in ["helper", "moderator", "admin"]:
            return await ctx.send("Not a valid level! Level must be one of Helper, Moderator or Admin.")

        session = self.bot.dbsession()
        permissions_db_object = StaffRoles(guild_id=ctx.guild.id, role_id=role.id, staff_perms=level.lower())
        session.merge(permissions_db_object)
        session.commit()
        session.close()
        await ctx.send(f"Successfully set the {level} rank to the {target} role! <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.command(name="get-mod-roles", aliases=['getmodroles', 'getmodrole'])
    @commands.has_permissions(administrator=True)
    async def get_mod_roles(self, ctx):
        """
        Get the configured mod roles.
        :param ctx:
        :return:
        """
        session = self.bot.dbsession()
        msg = "```css\n"
        for row in session.query(StaffRoles).filter_by(guild_id=ctx.guild.id):
            role = discord.utils.get(ctx.guild.roles, id=row.role_id)
            msg += f"{row.staff_perms + ':':10} {role}\n"
        msg += "```"
        session.close()
        await ctx.send(msg)
    # End Snippet

    @commands.guild_only()
    @commands.command(name="delete-mod-roles")
    @commands.has_permissions(administrator=True)
    async def delete_mod_roles(self, ctx):
        """Delete the set mod roles"""
        session = self.bot.dbsession()
        staff_roles = StaffRoles
        guild_delete = session.query(staff_roles).filter_by(guild_id=ctx.guild.id).delete()
        if guild_delete is None:
            await ctx.send("You haven't setup any mod roles.")
            return
        session.commit()
        session.close()
        await ctx.send(f"All set mod roles for this guild have been reset")

    @commands.guild_only()
    @commands.command(name="set-toggleable-roles", aliases=["settoggleableroles", "settogglerole"])
    @commands.has_permissions(manage_roles=True)
    async def set_toggleable_roles(self, ctx, *, role: str):
        """Setup toggleable roles for users"""
        role = discord.utils.get(ctx.guild.roles, name=role)
        if not role:
            return await ctx.send("❌ That role does not exist.")
        session = self.bot.dbsession()
        roles = Roles(guild_id=ctx.guild.id, role_id=role.id)
        session.merge(roles)
        session.commit()
        session.close()
        await ctx.send(f"{role} has been saved to the database.")

    @commands.guild_only()
    @commands.command(name="remove-toggleable-roles", aliases=['removetoggleableroles'])
    @commands.has_permissions(manage_roles=True)
    async def remove_toggleable_role(self, ctx):
        """This deletes all the toggleable roles you have set in this guild"""
        session = self.bot.dbsession()
        role = session.query(Roles).filter_by(guild_id=ctx.guild.id).delete()
        if role is None:
            await ctx.send("❌ There are no toggleable roles for this guild.")
            return
        session.commit()
        session.close()
        await ctx.send("All toggleable roles have been deleted.")

    @commands.guild_only()
    @commands.command(name="set-mute-role", aliases=['setmuterole'])
    @commands.has_permissions(administrator=True)
    async def set_mute_role(self, ctx, *, role_name: str):
        """Set the mute role for the server"""
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return await ctx.send(":x: I couldn't find that role.")

        session = self.bot.dbsession()
        try: # Here we go
            session.query(Config).filter_by(guild_id=ctx.guild.id).one()
            session.close()
            return await ctx.send("❌ This server already has a mute role setup.")
        except:
            mute_db = Config(guild_id=ctx.guild.id, mute_role_id=role.id)
            session.merge(mute_db)
            session.commit()
            session.close()
            await ctx.send(f"Successfully set the mute role to {role.name}")

    @commands.guild_only()
    @commands.command(name="reset-mute-role", aliases=['deletemuterole', 'delete-mute-role'])
    @commands.has_permissions(administrator=True)
    async def delete_mute_role(self, ctx):
        """This deletes whatever mute role is set for your server. 
        """
        session = self.bot.dbsession()
        try:
            mute = session.query(Config).filter_by(guild_id=ctx.guild.id).one()
            session.delete(mute)
            session.commit()
            session.close()
            await ctx.send("<:LightningCheck:571376826832650240> I successfully deleted the role from the database for this server.")
        except:
            mute = None
            session.close()
            return await ctx.send("❌ This server does not have a mute role setup.")

    @commands.group(aliases=['autoroles'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx):
        """Setup auto roles for the server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.guild_only()
    @autorole.command(name="set", aliases=['add'])
    @commands.has_permissions(manage_roles=True)
    async def setautoroles(self, ctx, *, role_name: str):
        """Set an auto role for the server"""
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return await ctx.send(":x: I couldn't find that role. **role_name is case sensitive**")

        session = self.bot.dbsession()
        query = session.query(AutoRoles).filter_by(guild_id=ctx.guild.id, role_id=role.id)
        if query.one_or_none() is not None:
            session.close()
            return await ctx.send("❌ That Role is Already Set as an Auto Role!")
        else:
            ar = AutoRoles(guild_id=ctx.guild.id, role_id=role.id)
            session.merge(ar)
            session.commit()
            session.close()
            await ctx.send(f"Successfully added auto role for {role.name}")

    @commands.guild_only()
    @autorole.command(name='remove')
    @commands.has_permissions(manage_roles=True)
    async def removeautoroles(self, ctx, *, role_name: str):
        """Removes a specific auto role that's configured"""
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return await ctx.send(":x: I couldn't find that role. **role_name is case sensitive**")
        session = self.bot.dbsession()
        gd = session.query(AutoRoles).filter_by(guild_id=ctx.guild.id, role_id=role.id)
        if gd.one_or_none() is None:
            await ctx.send("Not a valid auto role.")
            return
        else:
            gd.delete()
            session.commit()
            session.close()
            await ctx.send(f"Successfully removed {role.name}")

    @commands.guild_only()
    @autorole.command(name='list', aliases=['show'])
    @commands.has_permissions(manage_roles=True)
    async def showautoroles(self, ctx):
        """Lists all the auto roles this guild has"""
        session = self.bot.dbsession()
        embed = discord.Embed(title="Auto Roles", description="", color=discord.Color(0x5f9ff6))
        for row in session.query(AutoRoles).filter_by(guild_id=ctx.guild.id):
            role = discord.utils.get(ctx.guild.roles, id=row.role_id)
            embed.description += f"\N{BULLET} {role.name} (ID: {role.id})\n"
        if len(embed.description) == 0:
            embed.description += "No Auto Roles are setup for this server!"
        await ctx.send(embed=embed)

    @commands.group(aliases=['prefixes'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx):
        """Setup custom prefixes"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @prefix.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addprefix(self, ctx, prefix: Prefix):
        """Adds a custom prefix.


        To have a prefix with a word (or words), you should quote it and 
        end it with a space, e.g. "lightning " to set the prefix 
        to "lightning ". This is because Discord removes spaces when sending 
        messages so the spaces are not preserved."""
        if len(get_guild_prefixes(ctx.guild)) < 10:
            add_prefix(ctx.guild, prefix)
        else:
            return await ctx.send("You can only have 10 custom prefixes per guild! Please remove one.")
        await ctx.send(f"Added `{prefix}`")

    @prefix.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def rmprefix(self, ctx, prefix: Prefix):
        """Removes a custom prefix.
        
        The inverse of the prefix add command.
        
        To remove word/multi-word prefixes, you need to quote it.
        Example: l.prefix remove "lightning " removes the "lightning " prefix
        """
        if prefix in get_guild_prefixes(ctx.guild):
            remove_prefix(ctx.guild, prefix)
        else:
            return await ctx.send(f"`{prefix}` was never added as a custom prefix.")
        await ctx.send(f"Removed `{prefix}`")

    @prefix.command(name="list")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def listprefixes(self, ctx):
        """Lists all the custom prefixes this server has"""
        embed = discord.Embed(title=f"Custom Prefixes Set for {ctx.guild.name}", description="", 
                              color=discord.Color(0xd1486d))
        for p in get_guild_prefixes(ctx.guild):
            embed.description += f"- `{p}`\n"
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        session = self.bot.dbsession()
        query = session.query(AutoRoles).filter(AutoRoles.guild_id == member.guild.id)
        roles = [discord.utils.get(member.guild.roles, id=row.role_id) for row in query.all()]
        try:
            await member.add_roles(*roles)
        except:
            pass


def setup(bot):
    bot.add_cog(Configuration(bot))