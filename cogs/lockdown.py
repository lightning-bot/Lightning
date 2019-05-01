import discord
from discord.ext import commands
import db.per_guild_config
import db.mod_check

class Lockdown(commands.Cog):
    """Channel Lockdown Commands"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

    # Snippet from kirigiri
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    @commands.command(aliases=['lockdown'])
    async def lock(self, ctx, channel: discord.TextChannel = None):
        """Locks down the channel mentioned. Moderators+

        If no channel was mentioned, it locks the channel the command was used in"""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already locked down. Use `{ctx.prefix}unlock` to unlock.")
            return

        await channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)
        await channel.send(f"🔒 {channel.mention} is now locked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔒 **Lockdown**: {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"

        if "log_channel" in ctx.guild_config:
            try:
                log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
                await log_channel.send(log_message)
            except:
                pass

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @db.mod_check.check_if_at_least_has_staff_role("Admin")
    @commands.command(aliases=['hard-lock'])
    async def hlock(self, ctx, channel: discord.TextChannel = None):
        """Hard locks a channel. Sets the channel permissions as @everyone can't speak or see the channel.
        
        If no channel was mentioned, it hard locks the channel the command was used in."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).read_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already hard locked. Use `{ctx.prefix}hard-unlock` to unlock the channel.")
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=False)
        await channel.send(f"🔒 {channel.mention} is now hard locked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔒 **Hard Lockdown**: {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"

        if "log_channel" in ctx.guild_config:
            try:
                log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
                await log_channel.send(log_message)
            except:
                pass

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    @commands.command()
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        """Unlocks the channel mentioned. Moderators+ 

        If no channel was mentioned, it unlocks the channel the command was used in"""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).send_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return 

        await channel.set_permissions(ctx.guild.default_role, send_messages=None, add_reactions=None)
        await channel.send(f"🔓 {channel.mention} is now unlocked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔓 **Unlock**: {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"

        if "log_channel" in ctx.guild_config:
            try:
                log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
                await log_channel.send(log_message)
            except:
                pass

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @db.mod_check.check_if_at_least_has_staff_role("Admin")
    @commands.command(aliases=['hard-unlock'])
    async def hunlock(self, ctx, channel: discord.TextChannel = None):
        """Hard unlocks the channel mentioned. Admin only. 

        If no channel was mentioned, it unlocks the channel the command was used in"""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).read_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return 

        await channel.set_permissions(ctx.guild.default_role, read_messages=None)
        await channel.send(f"🔓 {channel.mention} is now unlocked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔓 **Hard Unlock**: {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"

        if "log_channel" in ctx.guild_config:
            try:
                log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
                await log_channel.send(log_message)
            except:
                pass


        

            



def setup(bot):
    bot.add_cog(Lockdown(bot))