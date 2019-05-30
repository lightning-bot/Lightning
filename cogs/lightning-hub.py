from discord.ext import commands
import discord

class LightningHub(commands.Cog):
    """Helper commands for Lightning Hub only."""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command(hidden=True)
    @commands.has_any_role("Trusted", "Verified")
    async def sr(self, ctx, *, text: str = ""):
        """Request staff assistance"""
        if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != 527887739178188830:
            return
        
        staff = self.bot.get_channel(536376192727646208)
        if text:
            # Prevent extra mentions. We'll clean this later.
            embed = discord.Embed(color=discord.Color.red())
            embed.description = text
            embed.add_field(name="Jump!", value=f"{ctx.message.jump_url}")
        await staff.send(f"‼ {ctx.author.mention} needs a staff member. @here", embed=(embed if text != "" else None))

    @commands.command(hidden=True)
    @commands.has_any_role("Helpers", "Staff")
    async def probate(self, ctx, target: discord.Member, *, reason: str = ""):
        if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != 527887739178188830:
            return

        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=546379342943617025)
        dm_message = f"You were probated on {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents kick issues in cases where user blocked bot
            # or has DMs disabled
            pass
        await target.add_roles(role, reason=str(ctx.author))
        msg = f"❗️ **Probate**: {ctx.author.mention} probated {target.mention} | {safe_name}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                    f", it is recommended to use " \
                    f"`{ctx.prefix}probate <user> [reason]`" \
                    f" as the reason is automatically sent to the user."

        await mod_log_chan.send(msg)

    @commands.command(hidden=True)
    @commands.has_any_role("Helpers", "Staff")
    async def unprobate(self, ctx, target: discord.Member, *, reason: str = ""):
        if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != 527887739178188830:
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

        await mod_log_chan.send(msg)







def setup(bot):
    bot.add_cog(LightningHub(bot))