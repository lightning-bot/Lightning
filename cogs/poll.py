import discord
from discord.ext import commands


class Poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')


    @commands.command()
    async def poll(self, ctx, *, question: str):
        """Creates a simple poll with thumbs up, thumbs down, and shrug as reactions"""
        embed = discord.Embed(title="Poll", description=f'Question: {question}', color=discord.Color.dark_blue())
        embed.set_author(name=f'{ctx.author.name}', icon_url=f'{ctx.author.avatar_url}')
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await msg.add_reaction("🤷")


def setup(bot):
    bot.add_cog(Poll(bot))