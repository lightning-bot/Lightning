import discord
from discord.ext import commands

class Misc(commands.Cog, name='Misc Info'):
    """Misc. Information"""
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

    @commands.command(aliases=['ui'])
    @commands.guild_only()
    async def userinfo(self, ctx, *, member: discord.Member=None):
        """Shows userinfo"""

        if member is None:
            member = ctx.author

        embed1 = discord.Embed(title=f'User Info. for {member}', color=member.colour)
        embed1.set_thumbnail(url=f'{member.avatar_url}')
        embed1.add_field(name="Bot?", value=f"{member.bot}")
        embed1.add_field(name="Account Created On:", value=f"{member.created_at}", inline=True)
        embed1.add_field(name='Status:', value=f"{member.status}")
        embed1.add_field(name="Activity:", value=f"{member.activity.name if member.activity else None}", inline=True)
        embed1.add_field(name="Joined:", value=f"{member.joined_at}")
        embed1.add_field(name="Highest Role:", value=f"{member.top_role}", inline=True)
        embed1.set_footer(text=f'User ID: {member.id}')
        await ctx.send(embed=embed1)

    @commands.command()
    async def userinfoid(self, ctx, user_id):
        """Get userinfo by ID"""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            await ctx.send(f"❌ I couldn't find {user_id}.")
            return
        embed = discord.Embed(title=f"User Info for {user.name}", color=user.colour)
        embed.set_thumbnail(url=f"{user.avatar_url}")
        embed.add_field(name="Bot?", value=f"{user.bot}")
        embed.add_field(name="Account Creation Date:", value=f"{user.created_at}")
        embed.set_footer(text=f"User ID: {user.id}")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Misc(bot))