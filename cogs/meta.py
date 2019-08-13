# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

import discord
from datetime import datetime
import config
import platform
from discord.ext import commands
from typing import Union
from collections import Counter
from utils.paginator import Pages
import asyncio
import itertools

class NonGuildUser(commands.Converter):
    async def convert(self, ctx, argument):
        if argument.isdigit() is False:
            return await ctx.send("Not a valid user ID!")
        try:
            return await ctx.bot.fetch_user(argument)
        except discord.NotFound:
            return await ctx.send("Not a valid user ID!")

# Paginated Help Command taken from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/meta.py
# MIT Licensed - Copyright (c) 2015 Rapptz 
# https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt

class HelpPaginator(Pages):
    def __init__(self, help_command, ctx, entries, *, per_page=4):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.reaction_emojis.append(('\N{WHITE QUESTION MARK ORNAMENT}', self.show_bot_help))
        self.total = len(entries)
        self.help_command = help_command
        self.prefix = help_command.clean_prefix
        self.is_bot = False

    def get_bot_page(self, page):
        cog, description, commands = self.entries[page - 1]
        self.title = f'{cog} Commands'
        self.description = description
        return commands

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = self.description
        self.embed.title = self.title

        #if self.is_bot:
        #    value ='For more help, join the official bot support server: https://discord.gg/DWEaqMy'
        #    self.embed.add_field(name='Support', value=value, inline=False)

        self.embed.set_footer(text=f'Use "{self.prefix}help command" for more info on a command.')

        for entry in entries:
            signature = f'{entry.qualified_name} {entry.signature}'
            self.embed.add_field(name=signature, value=entry.short_doc or "No help given", inline=False)

        if self.maximum_pages:
            self.embed.set_author(name=f'Page {page}/{self.maximum_pages} ({self.total} commands)')

    async def show_help(self):
        """shows this message"""

        self.embed.title = 'Paginator help'
        self.embed.description = 'Hello! Welcome to the help page.'

        messages = [f'{emoji} {func.__doc__}' for emoji, func in self.reaction_emojis]
        self.embed.clear_fields()
        self.embed.add_field(name='What are these reactions for?', value='\n'.join(messages), inline=False)

        self.embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(embed=self.embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())

    async def show_bot_help(self):
        """shows how to use the bot"""

        self.embed.title = 'Using the bot'
        self.embed.description = 'Hello! Welcome to the help page.'
        self.embed.clear_fields()

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            ('[A|B]', 'This means the it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n' \
                              'Now that you know the basics, it should be noted that...\n' \
                              '__**You do not type in the brackets!**__')
        )

        self.embed.add_field(name='How do I use this bot?', value='Reading the bot signature is pretty simple.')

        for name, value in entries:
            self.embed.add_field(name=name, value=value, inline=False)

        self.embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(embed=self.embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())

class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'cooldown': commands.Cooldown(1, 3.0, commands.BucketType.member),
            'help': 'Shows help about the bot, a command, or a category'
        })

    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = f'[{command.name}|{aliases}]'
            if parent:
                fmt = f'{parent} {fmt}'
            alias = fmt
        else:
            alias = command.name if not parent else f'{parent} {command.name}'
        return f'{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bNo Category'

        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        nested_pages = []
        per_page = 9
        total = 0

        for cog, commands in itertools.groupby(entries, key=key):
            commands = sorted(commands, key=lambda c: c.name)
            if len(commands) == 0:
                continue

            total += len(commands)
            actual_cog = bot.get_cog(cog)
            # get the description if it exists (and the cog is valid) or return Empty embed.
            description = (actual_cog and actual_cog.description) or discord.Embed.Empty
            nested_pages.extend((cog, description, commands[i:i + per_page]) for i in range(0, len(commands), per_page))

        # a value of 1 forces the pagination session
        pages = HelpPaginator(self, self.context, nested_pages, per_page=1)

        # swap the get_page implementation to work with our nested pages.
        pages.get_page = pages.get_bot_page
        pages.is_bot = True
        pages.total = total
        #await self.context.release()
        await pages.paginate()

    async def send_cog_help(self, cog):
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        pages = HelpPaginator(self, self.context, entries)
        pages.title = f'{cog.qualified_name} Commands'
        pages.description = cog.description

        #await self.context.release()
        await pages.paginate()

    def common_command_formatting(self, page_or_embed, command):
        page_or_embed.title = self.get_command_signature(command)
        if command.description:
            page_or_embed.description = f'{command.description}\n\n{command.help}'
        else:
            page_or_embed.description = command.help or 'No help found...'

    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=discord.Colour(0xf74b06))
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        pages = HelpPaginator(self, self.context, entries)
        self.common_command_formatting(pages, group)

        #await self.context.release()
        await pages.paginate()

class Meta(commands.Cog):
    """Commands related to Discord or the bot"""
    def __init__(self, bot):
        self.bot = bot
        self.original_help_command = bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.original_help_command

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

    @commands.command()
    async def support(self, ctx):
        """Sends an invite that goes to the support server"""
        try: 
            await ctx.author.send("Official Support Server Invite: https://discord.gg/cDPGuYd")
            await ctx.message.add_reaction("📬")
        except discord.Forbidden:
            await ctx.send("Official Support Server Invite: https://discord.gg/cDPGuYd")

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
        wbhk = discord.Webhook.from_url
        adp = discord.AsyncWebhookAdapter(self.bot.aiosession)
        webhook = wbhk(config.webhook_glog, adapter=adp)
        await webhook.execute(embed=embed)

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