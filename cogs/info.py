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
            return await ctx.send(f"**Here you go {ctx.author.name} \n<https://discord.gg/cDPGuYd>**")

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
        embed = discord.Embed(title="Lightning+")
        embed.set_author(name="UmbraSage#7867")
        embed.set_thumbnail(url="https://assets.gitlab-static.net/uploads/-/system/user/avatar/3717366/avatar.png?width=90")
        embed.url = "https://github.com/UmbraSage/Lightning.py"
        embed.description = "Lightning+, the successor to Lightning(.js)."
        embed.add_field(name="Latest Changes:", value=revision)
        embed.set_footer(text="Lightning+ 1.0.0")
        await ctx.send(embed=embed)


    @commands.command(aliases=['inviteme'])
    async def botinvite(self, ctx):
        """Invite Lightning+ to your server"""
        await ctx.send("You can invite me to your server with this link.\n<https://discordapp.com/api/oauth2/authorize?client_id=532220480577470464&permissions=8&scope=bot>")

    @commands.command(aliases=['sourcecode'])
    async def source(self, ctx):
        """My source code"""
        await ctx.send("This is my source code. https://github.com/UmbraSage/Lightning.py")

    @commands.command()
    async def ping(self, ctx):
        """Calculates the ping time.""" # Thanks discord.py's server
        pings = []
        number = 0
        typings = time.monotonic()
        await ctx.trigger_typing()
        typinge = time.monotonic()
        typingms = round((typinge - typings) * 1000)
        pings.append(typingms)
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
        await ctx.send(f"__**Ping Times:**__\nTyping: `{typingms}ms`  |  Latency: `{latencyms}ms`\nDiscord: `{discordms}`  |  Average: `{average}ms`")


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
