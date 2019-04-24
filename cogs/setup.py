import discord
from discord.ext import commands
import db.per_guild_config
from typing import Union
from database import StaffRoles, Roles

class Configuration(commands.Cog):
    """Server Configuration Commands"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

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
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.command(name="setjoinlogs")
    async def setjoinlogs(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the member join and leave logs"""
        if channel == "disable":
            ctx.guild_config.pop("join_log_channel")
            await ctx.send("Member join and leaves logging disabled.")
        else:
            ctx.guild_config["join_log_channel"] = channel.id
            await ctx.send(f"Member join and leaves logging set to {channel.mention} <:mayushii:562686801043521575>")

# Beta Feature
#    @commands.guild_only()
#    @commands.has_permissions(administrator=True)
#    @commands.command(name="setmodmailchannel")
#    async def setmodmailchannel(self, ctx, channel: Union[discord.TextChannel, str]):
#        """Set the Mod Mail Channel"""
#        if channel == "disable":
#            ctx.guild_config.pop("modmail_channel")
#            await ctx.send("Mod Mail has been disabled")
#        else:
#            ctx.guild_config["modmail_channel"] = channel.id
#           await ctx.send(f"Mod Mail has been set to {channel.mention}")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.command(name="setmodlogs")
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
    @commands.command(name="seteventlogs")
    async def set_event_logs(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set where events should be logged. 
        Such as Unbans, Bans, Nickname Changes."""
        if channel == "disable":
            ctx.guild_config.pop("events_channel")
            await ctx.send("Event logs have been disabled.")
        else:
            ctx.guild_config["event_channel"] = channel.id
            await ctx.send(f"Event logs have been set to {channel.mention} <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.command(name="set-message-log-channel", aliases=['setmsglogging'])
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
    @commands.command(aliases=['toggleinvitewatch', 'toggle-invite-watch'])
    async def setinvitewatch(self, ctx, channel: Union[discord.TextChannel, str]):
        """Set the Invite Watching Channel"""
        if channel == "disable":
            ctx.guild_config.pop("invite_watch")
            await ctx.send("Invite Watching has been disabled")
        else:
            ctx.guild_config["invite_watch"] = channel.id
            await ctx.send(f"Invite watching will be sent to {channel.mention}. Please note that this doesn't delete invites. <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.command(name="setmodrole", aliases=['setmodroles'])
    @commands.has_permissions(administrator=True)
    async def set_mod_role(self, ctx, target: str, level: str):
        """
        Set the various mod roles.
        :param target: Target role to set. Case specific.
        :param level: Any of "Helper", "Moderator" or "Admin".
        """
        role = discord.utils.get(ctx.guild.roles, name=target)
        if not role:
            return await ctx.send("That role does not exist.")

        if level.lower() not in ["helper", "moderator", "admin"]:
            return await ctx.send("Not a valid level! Level must be one of Helper, Moderator or Admin.")

        session = self.bot.db.dbsession()
        permissions_db_object = StaffRoles(guild_id=ctx.guild.id, role_id=role.id, staff_perms=level.lower())
        session.merge(permissions_db_object)
        session.commit()
        session.close()
        await ctx.send(f"Successfully set the {level} rank to the {target} role! <:mayushii:562686801043521575>")

    @commands.guild_only()
    @commands.command(name="getmodroles")
    @commands.has_permissions(administrator=True)
    async def get_mod_roles(self, ctx):
        """
        Get the configured mod roles.
        :param ctx:
        :return:
        """
        session = self.bot.db.dbsession()
        msg = "```css\n"
        for row in session.query(StaffRoles).filter_by(guild_id=ctx.guild.id):
            role = discord.utils.get(ctx.guild.roles, id=row.role_id)
            msg += f"{row.staff_perms + ':':10} {role}\n"
        msg += "```"
        session.close()
        await ctx.send(msg)
    # End Snippet

    @commands.guild_only()
    @commands.command(name="deletemodroles")
    @commands.has_permissions(administrator=True)
    async def delete_mod_roles(self, ctx):
        """Delete the set mod roles"""
        session = self.bot.db.dbsession()
        staff_roles = StaffRoles
        guild_delete = session.query(staff_roles).filter_by(guild_id=ctx.guild.id).delete()
        if guild_delete is None:
            await ctx.send("You haven't setup any mod roles.")
            return
        session.commit()
        session.close()
        await ctx.send(f"All set mod roles for this guild have been reset")

    @commands.guild_only()
    @commands.command(aliases=["settoggleableroles", "settogglerole"])
    @commands.has_permissions(manage_roles=True)
    async def set_toggleable_roles(self, ctx, role: str):
        """Setup toggleable roles for users"""
        role = discord.utils.get(ctx.guild.roles, name=role)
        if not role:
            return await ctx.send("❌ That role does not exist.")
        session = self.bot.db.dbsession()
        roles = Roles(guild_id=ctx.guild.id, role_id=role.id)
        session.merge(roles)
        session.commit()
        session.close()
        await ctx.send(f"{role} has been saved to the database.")

    @commands.guild_only()
    @commands.command(aliases=['removetoggleableroles'])
    @commands.has_permissions(manage_roles=True)
    async def remove_toggleable_role(self, ctx):
        """This deletes all the toggleable roles you have set in this guild"""
        session = self.bot.db.dbsession()
        role = session.query(Roles).filter_by(guild_id=ctx.guild.id).delete()
        if role is None:
            await ctx.send("❌ There are no toggleable roles for this guild.")
            return
        session.commit()
        session.close()
        await ctx.send("All toggleable roles have been deleted.")




def setup(bot):
    bot.add_cog(Configuration(bot))