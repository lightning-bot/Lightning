import discord
import aiohttp
import datetime
import time
import os
import config
from discord.ext import commands



class Info(commands.Cog):
    """Various information about the bot"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

    @commands.command()
    async def supportserver(self, ctx):
        """Gives an invite to the support server"""
        if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != 527887739178188830:
            return await ctx.send(f"**Here you go {ctx.author.mention} \n<https://discord.gg/cDPGuYd>**")

        await ctx.send(f"{ctx.author.mention} You're asking for an invite in the support server? <:blobthonk:537791813990350873>\n~~There's an invite in <#567138592208453635> btw~~")

    @commands.command()
    async def about(self, ctx):
        """About Lightning+"""
        #Snippet of code taken from RoboDanny. https://github.com/Rapptz/RoboDanny/blob/fb9c470b48e0333c58872d319cdbb9a42ec887c7/cogs/stats.py
        cmd = r'git show -s HEAD~3..HEAD --format="[{}](https://github.com/UmbraSage/Lightning.py/commit/%H) %s (%cr)"'
        if os.name == 'posix':
            cmd = cmd.format(r'\`%h\`')
        else:
            cmd = cmd.format(r'`%h`')

        try:
            revision = os.popen(cmd).read().strip()
        except OSError:
            revision = 'Could not fetch due to memory error. Sorry. :('
        embed = discord.Embed(title="Lightning+", color=discord.Color(0xf74b06))
        embed.set_author(name="UmbraSage#7867")
        embed.set_thumbnail(url="https://assets.gitlab-static.net/uploads/-/system/user/avatar/3717366/avatar.png?width=90")
        embed.url = "https://github.com/UmbraSage/Lightning.py"
        embed.description = "Lightning+, the successor to Lightning(.js)."
        embed.add_field(name="Latest Changes:", value=revision)
        embed.add_field(name="Servers", value=len(self.bot.guilds))
        embed.add_field(name="Links", value="[Bot Invite](https://discordapp.com/api/oauth2/authorize?client_id=532220480577470464&permissions=8&scope=bot)\n[Support Server](https://discord.gg/cDPGuYd)\n[DBL](https://discordbots.org/bot/532220480577470464)")
        embed.set_footer(text="Lightning+ 1.1.1") # We will do this later.
        await ctx.send(embed=embed)

    @commands.command()
    async def upvote(self, ctx):
        await ctx.send("You can vote for me here. <https://discordbots.org/bot/532220480577470464/vote>")

    @commands.command(aliases=['invite'])
    async def botinvite(self, ctx):
        """Invite Lightning+ to your server"""
        await ctx.send("You can invite me to your server with this link.\n<https://discordapp.com/api/oauth2/authorize?client_id=532220480577470464&permissions=8&scope=bot>")

    @commands.command(aliases=['sourcecode'])
    async def source(self, ctx):
        """My source code"""
        await ctx.send("This is my source code. https://github.com/UmbraSage/Lightning.py")

    @commands.command()
    async def ping(self, ctx):
        """Calculates the ping time."""
        pings = []
        number = 0
        await ctx.trigger_typing()
        latencyms = round(self.bot.latency * 1000)
        pings.append(latencyms)
        discords = time.monotonic()
        url = "https://discordapp.com/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status is 200:
                    discorde = time.monotonic()
                    discordms = round((discorde-discords)*1000)
                    pings.append(discordms)
                    discordms = f"{discordms}ms"
                else:
                    discordms = "Failed"
        for ms in pings:
            number += ms
        average = round(number / len(pings))
        embed = discord.Embed(title="🏓 Ping Times:", color=discord.Color.dark_red())
        embed.add_field(name="Latency", value=f"{latencyms}ms")
        embed.add_field(name="Discord", value=f"{discordms}")
        embed.set_footer(text=f"Average: {average}ms")
        await ctx.send(embed=embed)


    async def send_guild_info(self, embed, guild):
        embed.add_field(name='Guild Name', value=guild.name)
        embed.add_field(name='Guild ID', value=guild.id)
        member_count = guild.member_count
        embed.add_field(name='Member Count', value=str(member_count))
        embed.add_field(name='Owner', value=f"{guild.owner} | ID: {guild.owner.id}")
        log_channel = self.bot.get_channel(config.error_channel)
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = discord.Embed(title="Joined New Guild", color=discord.Color.blue())
        await self.send_guild_info(embed, guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        embed = discord.Embed(title="Left Guild", color=discord.Color.red())
        await self.send_guild_info(embed, guild)








def setup(bot):
    bot.add_cog(Info(bot))
