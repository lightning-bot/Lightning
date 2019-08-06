import discord
from datetime import datetime
import config
import platform
from discord.ext import commands
from typing import Union
from collections import Counter

class NonGuildUser(commands.Converter):
    async def convert(self, ctx, argument):
        if argument.isdigit() is False:
            return await ctx.send("Not a valid user ID!")
        try:
            return await ctx.bot.fetch_user(argument)
        except discord.NotFound:
            return await ctx.send("Not a valid user ID!")

class Meta(commands.Cog):
    """Commands related to Discord or the bot"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def avatar(self, ctx, *, member: Union[discord.Member, NonGuildUser] = None):
        """Displays a user's avatar."""
        if member is None:
            member = ctx.author
        embed = discord.Embed(color=discord.Color.blue(), 
                              description=f"[Link to Avatar]({member.avatar_url_as(static_format='png')})")
        embed.set_author(name=f"{member.name}\'s Avatar")
        embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(aliases=['ui'])
    async def userinfo(self, ctx, *, member: Union[discord.Member, NonGuildUser]=None):
        """Shows userinfo"""
        if member is None:
            member = ctx.author
        if not isinstance(member, discord.Member):
            embed = discord.Embed(title=f'User Info. for {member}')#, color=member.colour)
            embed.set_thumbnail(url=f'{member.avatar_url}')
            embed.add_field(name="Bot?", value=f"{member.bot}")
            var = member.created_at.strftime("%Y-%m-%d %H:%M")
            embed.add_field(name="Account Created On:", value=f"{var} UTC\n"
                            f"Relative Date: {self.bot.get_relative_timestamp(time_to=member.created_at, humanized=True)}")
            embed.set_footer(text='This member is not in this server.')
            return await ctx.send(embed=embed)
        embed = discord.Embed(title=f'User Info. for {member}', color=member.colour)
        embed.set_thumbnail(url=f'{member.avatar_url}')
        embed.add_field(name="Bot?", value=f"{member.bot}")
        var = member.created_at.strftime("%Y-%m-%d %H:%M")
        var2 = member.joined_at.strftime("%Y-%m-%d %H:%M")
        embed.add_field(name="Account Created On:", value=f"{var} UTC\n"
                        f"Relative Date: {self.bot.get_relative_timestamp(time_to=member.created_at, humanized=True)}")
        embed.add_field(name='Status:', value=f"{member.status}")
        embed.add_field(name="Activity:", value=f"{member.activity.name if member.activity else None}", inline=True)
        embed.add_field(name="Joined:", value=f"{var2} UTC\n"
                        f"Relative Date: {self.bot.get_relative_timestamp(time_to=member.joined_at, humanized=True)}")
        embed.add_field(name="Highest Role:", value=f"{member.top_role}\n")
        embed.set_footer(text=f'User ID: {member.id}')
        await ctx.send(embed=embed)

    @commands.command(aliases=['info', 'credits'])
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
        """Gives you a link to add Lightning to your server."""
        await ctx.send("You can invite me to your server with this link.\n"
                       "<https://discordapp.com/api/oauth2/authorize?client_id="
                       "532220480577470464&permissions=470150390&scope=bot>")

    @commands.command(hidden=True, aliases=['sourcecode'])
    async def source(self, ctx):
        """My source code"""
        await ctx.send("This is my source code. https://gitlab.com/LightSage/Lightning")

    @commands.command()
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

    @commands.guild_only()
    @commands.command(aliases=['server'])
    async def serverinfo(self, ctx):
        """Shows information about the server"""
        guild = ctx.guild # Simplify 
        embed = discord.Embed(title=f"Server Info for {guild.name}")
        embed.add_field(name='Owner', value=guild.owner)
        embed.add_field(name="ID", value=guild.id)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="Creation", value=guild.created_at)
        member_by_status = Counter(str(m.status) for m in guild.members) 
        # Little snippet taken from R. Danny. Under the MIT License
        sta = f'<:online:572962188114001921> {member_by_status["online"]} ' \
              f'<:idle:572962188201820200> {member_by_status["idle"]} ' \
              f'<:dnd:572962188134842389> {member_by_status["dnd"]} ' \
              f'<:offline:572962188008882178> {member_by_status["offline"]}\n\n' \
              f'Total: {guild.member_count}'    

        embed.add_field(name="Members", value=sta)
        embed.add_field(name="Emoji Count", value=f"{len(guild.emojis)}")
        embed.add_field(name="Verification Level", value=guild.verification_level)
        boosts = f"Tier: {guild.premium_tier}\n"\
                 f"Users Boosted Count: {guild.premium_subscription_count}"
        embed.add_field(name="Nitro Server Boost", value=boosts)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def membercount(self, ctx):
        """Prints the server's member count"""
        embed = discord.Embed(title=f"Member Count", 
                              description=f"{ctx.guild.name} has {ctx.guild.member_count} members.", 
                              color=discord.Color.orange())
        await ctx.send(embed=embed)

    async def send_guild_info(self, embed, guild):
        bots = sum(member.bot for member in guild.members)
        humans = guild.member_count - bots
        embed.add_field(name='Guild Name', value=guild.name)
        embed.add_field(name='Guild ID', value=guild.id)
        embed.add_field(name='Member Count', value=f"Bots: {bots}\nHumans: {humans}")
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
    bot.add_cog(Meta(bot))