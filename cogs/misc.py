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

    @commands.command(aliases=['hastebin'])
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.channel)
    async def pastebin(self, ctx, *, message: str):
        """Make a pastebin with your own message"""
        url = await self.bot.haste(message)
        await ctx.send(f"Here's your pastebin. {ctx.author.mention}\n{url}")


def setup(bot):
    bot.add_cog(Misc(bot))