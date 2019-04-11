import discord
import aiohttp
import datetime
import time
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
            return await ctx.send(f"**Here you go {ctx.author.name} \n<https://discord.gg/ZqU3XEw>**")

        await ctx.send(f"**{ctx.author}** You're asking for an invite in the support server? <:blobthonk:537791813990350873>\n~~There's an invite in <#527887739178188834> btw~~")

    @commands.command(aliases=['inviteme'])
    async def botinvite(self, ctx):
        """Invite Lightning+ to your server"""
        await ctx.send("You can invite me to your server with this link.\n<https://discordapp.com/api/oauth2/authorize?client_id=531163366799048716&permissions=8&scope=bot>")

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





def setup(bot):
    bot.add_cog(Info(bot))