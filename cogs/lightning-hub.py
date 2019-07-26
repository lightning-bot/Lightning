from discord.ext import commands
import discord
import db.per_guild_config
import db.mod_check
from utils.restrictions import add_restriction, remove_restriction

class LightningHub(commands.Cog):
    """Helper commands for Lightning Hub only."""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    # Snippet of Code taken from Noirscape's kirigiri. https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")

    @commands.guild_only()
    @commands.command(hidden=True)
    @commands.has_any_role("Trusted", "Verified")
    async def sr(self, ctx, *, text: str = ""):
        """Request staff assistance. Trusted and Verified only."""
        if ctx.guild.id != 527887739178188830:
            return
        
        staff = self.bot.get_channel(536376192727646208)
        if text:
            # Prevent extra mentions. We'll clean this later.
            embed = discord.Embed(color=discord.Color.red())
            embed.description = text
            embed.add_field(name="Jump!", value=f"{ctx.message.jump_url}")
        await staff.send(f"‼ {ctx.author.mention} needs a staff member. @here", embed=(embed if text != "" else None))
        await ctx.message.add_reaction("✅")
        await ctx.send("Online staff have been notified of your request.")

    @commands.guild_only()
    @commands.command(hidden=True)
    @commands.has_any_role("Helpers", "Staff")
    async def probate(self, ctx, target: discord.Member, *, reason: str = ""):
        """Probates a user. Staff only."""
        if ctx.guild.id != 527887739178188830:
            return

        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=546379342943617025)
        dm_message = f"You were probated on {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."

        await target.add_roles(role, reason=str(ctx.author))
        msg = f"❗️ **Probate**: {ctx.author.mention} probated {target.mention} | {safe_name}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                    f", it is recommended to use " \
                    f"`{ctx.prefix}probate <user> [reason]`" \
                    f" as the reason is automatically sent to the user."
        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents issues in cases where user blocked bot
            # or has DMs disabled
            msg += f"\n\n{target.mention} has their DMs off and I was unable to send the reason."# Experimental
            pass

        add_restriction(ctx.guild, target.id, role.id)
        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now probated.")

    @commands.guild_only()
    @commands.command(hidden=True)
    @commands.has_any_role("Helpers", "Staff")
    async def unprobate(self, ctx, target: discord.Member, *, reason: str = ""):
        """Removes probation role/unprobates the user. Staff only."""
        if ctx.guild.id != 527887739178188830:
            return

        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=546379342943617025)
        
        await target.remove_roles(role, reason=str(ctx.author))
        msg = f"❗️ **Unprobate**: {ctx.author.mention} unprobated {target.mention} | {safe_name}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                    f", it is recommended to use " \
                    f"`{ctx.prefix}unprobate <user> [reason]`" 

        remove_restriction(ctx.guild, target.id, role.id)
        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now unprobated.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        if member.guild.id != 527887739178188830:
            return
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "auto_probate" in config:
                role = discord.Object(id=546379342943617025)
                await member.add_roles(role, reason="Auto Probate")
                dm_message = f"You were automatically probated. Please read the rules for this server and speak in the probation channel when you are ready."
                msg = f"**Auto Probate:** {member.mention}"
                try:
                    await member.send(dm_message)
                except discord.errors.Forbidden:
                    msg += "\nUnable to deliver message in DMs"
                mod_log_chan = self.bot.get_channel(552583376566091805)
                await mod_log_chan.send(msg)

    @commands.command(hidden=True)
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def autoprobate(self, ctx, status="on"):
        """Turns on or off auto probate. 
        Use "disable" to disable auto probate."""
        if ctx.guild.id != 527887739178188830:
            return

        if status == "disable":
            ctx.guild_config.pop("auto_probate")
            await ctx.send("Auto Probate is now disabled.")
        else:
            ctx.guild_config["auto_probate"] = ctx.author.id
            await ctx.send(f"Auto Probate is now enabled\nTo turn off Auto Probate in the future, use `{ctx.prefix}autoprobate disable`")

    @commands.command(hidden=True)
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def elevate(self, ctx):
        """Gains the elevated role. Use with care!"""
        if ctx.guild.id != 527887739178188830:
            return
        target = ctx.author
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=527996858908540928)

        await target.add_roles(role, reason=str(ctx.author))
        msg = f"🚑️ **Elevated**: {ctx.author.mention} | {safe_name}"

        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now elevated!")

    @commands.command(hidden=True, aliases=['unelevate'])
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def deelevate(self, ctx):
        """Removes the elevated role. Use with care."""
        if ctx.guild.id != 527887739178188830:
            return
        target = ctx.author
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=527996858908540928)

        await target.remove_roles(role, reason=str(ctx.author))
        msg = f"❗️ **De-elevated**: {ctx.author.mention} | {safe_name}"

        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now unelevated!")


def setup(bot):
    bot.add_cog(LightningHub(bot))
