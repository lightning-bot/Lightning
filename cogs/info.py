import discord
import datetime
from datetime import datetime
import time
import config
import platform
from discord.ext import commands


class Info(commands.Cog):
    """Bot Info Cog"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    async def supportserver(self, ctx):
        """Gives an invite to the support server"""
        if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != 527887739178188830:
            return await ctx.send(f"**Here you go {ctx.author.mention} \n<https://discord.gg/cDPGuYd>**")

        await ctx.send(f"{ctx.author.mention} You're asking for an invite in the support server? "
                       "<:blobthonk:537791813990350873>\n~~There's an invite in <#567138592208453635> btw~~")

    @commands.command(aliases=['info', 'credits'])
    @commands.bot_has_permissions(embed_links=True)
    async def about(self, ctx):
        """Various information about the bot."""
        all_members = sum(1 for _ in ctx.bot.get_all_members())
        bot_owner = self.bot.get_user(self.bot.owner_id)
        embed = discord.Embed(title="Lightning", color=discord.Color(0xf74b06))
        embed.set_author(name="TwilightSage#7867", icon_url=bot_owner.avatar_url)
        embed.url = "https://gitlab.com/LightSage/Lightning"
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        embed.description = f"Lightning.py, the successor to Lightning(.js)"
        embed.add_field(name="Servers", value=len(self.bot.guilds))
        embed.add_field(name="Members", value=all_members)
        embed.add_field(name="Python Version", value=f"{platform.python_implementation()} {platform.python_version()}")
        embed.add_field(name="Stats", value=f"{self.bot.successful_command} commands used since boot.\n"
                                            f"{len(self.bot.commands)} total commands.\n")
        embed.add_field(name="Links", value="[Bot Invite](https://discordapp.com/api/oauth2/authorize?client_id="
                                            "532220480577470464&permissions=8&scope=bot)\n[Support Server]"
                                            "(https://discord.gg/cDPGuYd)\n[DBL](https://discordbots.org/bot/"
                                            "532220480577470464)\n[Website](https://lightsage.gitlab.io/lightning/home/)")
        embed.set_footer(text=f"Lightning {self.bot.version}")
        await ctx.send(embed=embed)

    @commands.command(aliases=['invite'])
    async def botinvite(self, ctx):
        """Invite Lightning to your server"""
        await ctx.send("You can invite me to your server with this link.\n"
                       "<https://discordapp.com/api/oauth2/authorize?client_id="
                       "532220480577470464&permissions=470150390&scope=bot>")

    @commands.command(hidden=True, aliases=['sourcecode'])
    async def source(self, ctx):
        """My source code"""
        await ctx.send("This is my source code. https://gitlab.com/LightSage/Lightning")

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def ping(self, ctx):
        """Calculates the ping time."""
        await ctx.trigger_typing()
        latencyms = round(self.bot.latency * 1000)
        embed = discord.Embed(title="🏓 Ping Time:", color=discord.Color.dark_red())
        embed.add_field(name="Latency", value=f"{latencyms}ms")
        await ctx.send(embed=embed)

    @commands.command()
    async def uptime(self, ctx):
        """Displays my uptime"""
        delta_uptime = datetime.utcnow() - self.bot.launch_time
        hours, remainder = divmod(int(delta_uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        await ctx.send(f"My uptime is: {days}d, {hours}h, {minutes}m, {seconds}s <:meowbox:563009533530734592>")


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
        self.bot.log.info(f"Left Guild | {guild.name} | {guild.id}")
        await self.send_guild_info(embed, guild)


def setup(bot):
    bot.add_cog(Info(bot))