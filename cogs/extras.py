import discord
import random
import time
import datetime
from database import Roles, Base
from discord.ext import commands
import aiohttp
import db.mod_check


class Extras(commands.Cog):
    """Extra stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    async def peng(self, ctx):
        """Uhhh ping?"""
        await ctx.send(f"My ping is uhhh `{random.randint(31,150)}ms`")


    @commands.command()
    @commands.guild_only()
    async def avatar(self, ctx, *, member: discord.Member = None):
        """Get someone's avatar."""
        if member is None:
            member = ctx.author
        embed = discord.Embed(color=discord.Color.blue(), description=f"[Link to Avatar]({member.avatar_url})")
        embed.set_author(name=f"{member.name}\'s Avatar")
        embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)
        
    @commands.command(aliases=['say'])
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def speak(self, ctx, channel: discord.TextChannel, *, inp):
        """Say something through the bot to the specified channel. Staff only."""
        await channel.trigger_typing()
        await channel.send(inp)
    
    @commands.guild_only()
    @commands.command(aliases=['listemojis', 'listemoji'])
    async def listemotes(self, ctx):
        """Prints a fancy list of the server's emotes"""
        if len(ctx.guild.emojis) == 0:
            return await ctx.send("This server has no emotes!")
            
        paginator = commands.Paginator(suffix='', prefix='')
        for emoji in ctx.guild.emojis:
            paginator.add_line(f'{emoji} -- `{emoji}`')

        for page in paginator.pages:
            await ctx.send(page)

    @commands.command()
    async def inviteinfo(self, ctx, invite_code: discord.Invite):
        embed = discord.Embed(title=f'Invite for {invite_code.guild.name} '
                                    f"({invite_code.guild.id})")
        embed.add_field(name='Channel', value=f'{invite_code.channel.name} '
                                              f'({invite_code.channel.id})', inline=False)
        embed.add_field(name='Uses', value=invite_code.uses, inline=False)
        if invite_code.inviter:
            embed.add_field(name='Inviter', value=invite_code.inviter, inline=False)
        embed.add_field(name="Created", value=invite_code.created_at)
        if invite_code.temporary is True:
            embed.description += "✅ Temporary Invite"
        await ctx.send(embed=embed)
        await ctx.send(f"{invite_code.max_age} {invite_code.approximate_member_count}"
                       f"{invite_code.id} {invite_code.url}")


def setup(bot):
    bot.add_cog(Extras(bot))