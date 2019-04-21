import discord
from discord.ext import commands

class Misc(commands.Cog, name='Misc Info'):
    """Misc. information"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

    @commands.command()
    @commands.guild_only()
    async def topic(self, ctx, *, channel: discord.TextChannel = None):
        """Quote the channel topic."""
        if channel is None:
            channel = ctx.message.channel
        embed = discord.Embed(title=f"Channel Topic for {channel}", description=f"{channel.topic}", color=discord.Color.dark_blue())
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Misc(bot))