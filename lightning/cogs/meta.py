"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations

import asyncio
import collections
import inspect
import json
import logging
import os
import time
from typing import TYPE_CHECKING

import discord
import psutil
from discord.ext import commands, menus
from rapidfuzz.process import extractOne

from lightning import LightningCog, LightningContext
from lightning import command as lcommand
from lightning import group as lgroup
from lightning.converters import GuildorNonGuildUser, Message, ReadableChannel
from lightning.errors import ChannelPermissionFailure, MessageNotFoundInChannel
from lightning.utils import helpers
from lightning.utils.paginator import InfoMenuPages
from lightning.utils.time import natural_timedelta

if TYPE_CHECKING:
    from lightning import LightningBot

log = logging.getLogger(__name__)
flag_name_lookup = {"HumanTime": "Time", "FutureTime": "Time"}


class HelpPaginatorMenu(InfoMenuPages):
    def __init__(self, help_command, ctx, source, **kwargs):
        super().__init__(source, clear_reactions_after=True, check_embeds=True, **kwargs)
        self.help_command = help_command
        self.total = len(source.entries)
        self.ctx = ctx
        self.is_bot = False

    @menus.button("\N{WHITE QUESTION MARK ORNAMENT}", position=menus.Last(5))
    async def show_bot_help(self, payload) -> None:
        """shows how to use the bot"""
        embed = discord.Embed(color=discord.Color.blurple())
        embed.title = 'Using the bot'
        embed.description = 'Hello! Welcome to the help page.'

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            ('[A|B]', 'This means it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n'
                              'Now that you know the basics, it should be noted that...\n'
                              '__**You do not type in the brackets!**__')
        )

        embed.add_field(name='How do I use this bot?',
                        value='Reading the bot signature is pretty simple.')

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f'We were on page {self.current_page + 1} before this message.')
        await self.message.edit(embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_page(self.current_page)

        self.bot.loop.create_task(go_back_to_current_page())

    async def paginate(self, **kwargs) -> None:
        await super().start(self.ctx, **kwargs)


class HelpMenu(menus.ListPageSource):
    def __init__(self, data, *, per_page=4, embed=None, bot_help=False):
        self.embed = embed
        self.bot_help = bot_help
        self.data = data if bot_help is True else None
        self.total = len(data)
        data = sorted(data.keys()) if bot_help is True else data
        super().__init__(data, per_page=per_page)

    def format_category_embed(self, embed: discord.Embed, menu, entries: list) -> discord.Embed:
        description = f"Use \"{menu.ctx.clean_prefix}help [command]\" for help about a command.\nYou can also use \""\
                      f"{menu.ctx.clean_prefix}help [category]\" for help about a category."
        if "support_server_invite" in menu.bot.config['bot']:
            description += "\nFor additional help, join the support server: "\
                           f"{menu.bot.config['bot']['support_server_invite']}"
        embed.description = description

        def format_commands(c):
            # TODO: Handle if embed length is too long
            return " | ".join([f"`{cmd.qualified_name}`" for cmd in c])

        for entry in entries:
            cmds = sorted(self.data.get(entry, []), key=lambda d: d.qualified_name)
            cog = cmds[0].cog
            value = f"{cog.description}\n{format_commands(cmds)}" if cog.description else format_commands(cmds)
            embed.add_field(name=entry, value=value, inline=False)

        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()} ({self.total} categories)",
                         icon_url=menu.ctx.bot.user.avatar.url)
        return embed

    def format_group_embed(self, embed: discord.Embed, menu, entries: list) -> discord.Embed:
        for command in entries:
            signature = f"{command.qualified_name} {command.signature}"
            embed.add_field(name=signature, value=command.short_doc or "No help found...", inline=False)

        embed.set_author(name=f"Page {menu.current_page + 1} of {self.get_max_pages()} ({self.total} commands)",
                         icon_url=menu.ctx.bot.user.avatar.url)
        return embed

    async def format_page(self, menu, entries) -> discord.Embed:
        if self.embed:
            embed = self.embed
            embed.clear_fields()
        else:
            embed = discord.Embed(color=0xf74b06)

        if self.bot_help is True:
            embed = self.format_category_embed(embed, menu, entries)
        else:
            embed = self.format_group_embed(embed, menu, entries)
            embed.set_footer(text=menu.help_command.get_ending_note())
        return embed


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'cooldown': commands.CooldownMapping(commands.Cooldown(1, 3.0), commands.BucketType.member),
            'help': 'Shows help about the bot, a command, or a category'
        })

    def get_ending_note(self) -> str:
        return f'Use {self.context.clean_prefix}{self.invoked_with} [command] for more info on a command.'

    async def command_not_found(self, string) -> str:
        output = f"No command called \"{string}\" found."
        commands = [c.qualified_name for c in await self.filter_commands(self.context.bot.commands)]
        if fuzzymatches := extractOne(string, commands, score_cutoff=70):
            output += f" Did you mean \"{fuzzymatches[0]}\"?"
        return output

    def get_command_signature(self, command) -> str:
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = f'[{command.name}|{aliases}]'
            if parent:
                fmt = f'{parent} {fmt}'
            alias = fmt
        else:
            alias = command.name if not parent else f'{parent} {command.name}'
        return f'{alias}'

    async def send_bot_help(self, mapping) -> None:
        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True)
        commands = {}
        for command in entries:
            try:
                commands[command.cog.qualified_name or "No Category"].append(command)
            except KeyError:
                commands[command.cog.qualified_name or "No Category"] = [command]

        pages = HelpPaginatorMenu(self, self.context, HelpMenu(commands, bot_help=True))
        await pages.paginate()

    async def send_cog_help(self, cog) -> None:
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        embed = discord.Embed(title=f'{cog.qualified_name} Commands', description=cog.description or '', color=0xf74b06)
        pages = HelpPaginatorMenu(self, self.context, HelpMenu(entries, embed=embed, per_page=5))
        await pages.paginate()

    def flag_help_formatting(self, command):
        if not hasattr(command.callback, "__lightning_argparser__"):
            return

        flagopts = []
        all_flags = command.callback.__lightning_argparser__.get_all_unique_flags()
        for flag in all_flags:
            if flag.is_bool_flag is True:
                arg = 'No argument'
            else:
                name = flag.converter.__name__
                arg = flag_name_lookup[name] if name in flag_name_lookup else name
            fhelp = flag.help or "No help found..."
            flagopts.append(f'`{", ".join(flag.names)}` ({arg}): {fhelp}')
        return flagopts

    def permissions_required_format(self, command) -> tuple:
        guild_permissions = []
        channel_permissions = []

        for pred in command.checks:
            if hasattr(pred, 'guild_permissions'):
                guild_permissions.extend(pred.guild_permissions)
            elif hasattr(pred, 'channel_permissions'):
                channel_permissions.extend(pred.channel_permissions)

        return (channel_permissions, guild_permissions)

    def common_command_formatting(self, page_or_embed, command):
        page_or_embed.title = self.get_command_signature(command)
        if command.signature:
            usage = f"**Usage**: {command.qualified_name} {command.signature}\n\n"
        else:
            usage = f"**Usage**: {command.qualified_name}\n\n"

        desc = [usage]

        if command.description:
            desc.append(command.description.format(prefix=self.context.clean_prefix))
            if command.help:
                desc.append(f"\n\n{command.help.format(prefix=self.context.clean_prefix)}")
        elif command.help:
            desc.append(command.help.format(prefix=self.context.clean_prefix))
        else:
            desc.append("No help found...")

        if hasattr(command, 'level'):
            desc.append(f"\n\n**Default Level Required**: {command.level.name}")

        if cflags := self.flag_help_formatting(command):
            page_or_embed.add_field(name="Flag options", value="\n".join(cflags))

        channel, guild = self.permissions_required_format(command)
        if channel:
            req = ", ".join(channel).replace('_', ' ').replace('guild', 'server').title()
            desc.append(f"\n**Channel Permissions Required**: {req}")
        if guild:
            req = ", ".join(guild).replace('_', ' ').replace('guild', 'server').title()
            desc.append(f"\n**Server Permissions Required**: {req}")

        page_or_embed.description = ''.join(desc)

    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=0xf74b06)
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        embed = discord.Embed(colour=0xf74b06)
        self.common_command_formatting(embed, group)
        pages = HelpPaginatorMenu(self, self.context, HelpMenu(entries, embed=embed, per_page=5))
        await pages.paginate()


class Meta(LightningCog):
    """Commands related to Discord or the bot"""

    def __init__(self, bot: LightningBot):
        self.bot = bot
        self.original_help_command = bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self
        self.unavailable_guilds = []
        self.process = psutil.Process()

    def cog_unload(self):
        self.bot.help_command = self.original_help_command

    @lcommand(aliases=['avy'])
    async def avatar(self, ctx: LightningContext, *, member: GuildorNonGuildUser = commands.default.Author) -> None:
        """Displays a user's avatar"""
        parts = []
        if hasattr(member, 'guild_avatar') and member.guild_avatar:
            parts.append(f"[Link to guild avatar]({member.guild_avatar.with_static_format('png')})")
        if member.avatar:
            parts.append(f"[Link to avatar]({member.avatar.with_static_format('png')})")
        if member.default_avatar:
            parts.append(f"[Link to default avatar]({member.default_avatar.url})")
        embed = discord.Embed(color=discord.Color.blue(), description='\n'.join(parts))
        embed.set_author(name=f"{member.name}\'s Avatar")
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @lcommand(aliases=['ui'])
    async def userinfo(self, ctx: LightningContext, *, member: GuildorNonGuildUser = commands.default.Author) -> None:
        """Gives information about a member or a user"""
        embed = discord.Embed(title=str(member), color=member.colour, description=f"**ID**: {member.id}")
        embed.set_thumbnail(url=member.display_avatar.url)

        if member.bot:
            embed.description += "\nThis user is a bot."

        embed.add_field(name="Account Created On", value=f"{discord.utils.format_dt(member.created_at)} "
                        f"({natural_timedelta(member.created_at, accuracy=3)})",
                        inline=False)

        if member == self.bot.user:
            embed.add_field(name="Shared Servers", value=len(self.bot.guilds))
        else:
            embed.add_field(name="Shared Servers", value=len(member.mutual_guilds))

        if not isinstance(member, discord.Member):
            embed.set_footer(text='This member is not in this server.')

        # TODO: Support multiple activities
        activity = getattr(member, 'activity', None)
        if activity is not None:
            if isinstance(member.activity, discord.Spotify):
                artists = ', '.join(member.activity.artists)
                spotifyact = f"Listening to [{member.activity.title}]"\
                             f"(https://open.spotify.com/track/{member.activity.track_id})"\
                             f" by {artists}"
                embed.add_field(name="Activity", value=spotifyact, inline=False)
            elif isinstance(member.activity, discord.Streaming):
                embed.add_field(name="Activity", value=f"Streaming [{member.activity.name}]"
                                                       f"({member.activity.url})", inline=False)
            elif isinstance(member.activity, discord.CustomActivity):
                act_name = activity.name if activity.name is not None else ""
                activity = f"{activity.emoji} {act_name}" if activity.emoji else act_name
                embed.add_field(name="Activity", value=activity, inline=False)
            else:
                embed.add_field(name="Activity", value=member.activity.name, inline=False)

        if hasattr(member, 'joined_at'):
            embed.add_field(name="Joined", value=f"{discord.utils.format_dt(member.joined_at)} "
                            f"({natural_timedelta(member.joined_at, accuracy=3)})",
                            inline=False)

        if hasattr(member, 'roles'):
            roles = [x.mention for x in member.roles if not x.is_default()]
            if roles:
                revrole = reversed(roles)
                embed.add_field(name=f"Roles [{len(roles)}]",
                                value=" ".join(revrole) if len(roles) < 10 else "Cannot show all roles",
                                inline=False)
        await ctx.send(embed=embed)

    @lcommand()
    @commands.guild_only()
    async def roleinfo(self, ctx: LightningContext, *, role: discord.Role) -> None:
        """Gives information for a role"""
        em = discord.Embed(title=role.name, color=role.color)
        desc = [f"**Creation**: {natural_timedelta(role.created_at, accuracy=3)}",
                f"**Color**: {role.color}", f"**ID**: {role.id}", f"{len(role.members)} members have this role."]

        allowed = []
        for name, value in role.permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
        em.add_field(name="Permissions",
                     value=f"**Value**: {role.permissions.value}\n\n" + ", ".join(allowed),
                     inline=False)

        if role.managed:
            desc.append("This role is managed by an integration of some sort.")

        em.description = "\n".join(desc)
        await ctx.send(embed=em)

    @lcommand()
    async def spotify(self, ctx: LightningContext, member: discord.Member = commands.default.Author) -> None:
        if member.status is discord.Status.offline:
            await ctx.send(f"{member} needs to be online in order for me to check their Spotify status.")
            return

        activity = None
        for act in member.activities:
            if isinstance(act, discord.Spotify):
                activity = act
                break

        if not activity:
            await ctx.send(f"{member} is not listening to Spotify with Discord integration."
                           " If that is wrong, then blame Discord's API.")
            return

        embed = discord.Embed(title=activity.title, color=0x1DB954)
        embed.set_thumbnail(url=activity.album_cover_url)
        embed.set_author(name=member, icon_url=member.avatar.url)
        embed.add_field(name="Artist", value=', '.join(activity.artists))
        embed.add_field(name="Album", value=activity.album, inline=False)

        duration_m, duration_s = divmod(activity.duration.total_seconds(), 60)
        current_m, current_s = divmod((discord.utils.utcnow() - activity.start).seconds, 60)
        embed.description = f"{'%d:%02d' % (current_m, current_s)} - {'%d:%02d' % (duration_m, duration_s)}"

        await ctx.send(embed=embed)

    async def get_bot_author(self):
        user = self.bot.get_user(376012343777427457)
        return user or await self.bot.fetch_user(376012343777427457)

    @lcommand()
    async def about(self, ctx: LightningContext) -> None:
        """Gives information about the bot."""
        embed = discord.Embed(title="Lightning", color=0xf74b06)
        if self.bot.owner_id:
            owners = [self.bot.get_user(self.bot.owner_id)]
        elif self.bot.owner_ids:
            owners = [self.bot.get_user(u) for u in self.bot.owner_ids]
        else:
            owners = []

        author = await self.get_bot_author()
        embed.set_author(name=str(author), icon_url=author.avatar.with_static_format('png'))

        description = [f"This bot instance is owned by {', '.join(str(o) for o in owners)}"]

        embed.url = self.bot.config['bot'].get("git_repo_url", "https://gitlab.com/lightning-bot/Lightning")
        embed.set_thumbnail(url=ctx.me.avatar.url)

        if self.bot.config['bot']['description']:
            description.append(f"**Description**: {self.bot.config['bot']['description']}")

        # Channels
        text = 0
        voice = 0
        for guild in self.bot.guilds:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    text += 1
                elif isinstance(channel, discord.VoiceChannel):
                    voice += 1
        embed.add_field(name="Channels", value=f"{text:,} text channels\n{voice:,} voice channels")

        # Members
        membertotal = 0
        membertotal_online = 0
        for member in self.bot.get_all_members():
            membertotal += 1
            if member.status is not discord.Status.offline:
                membertotal_online += 1
        all_members = f"Total: {membertotal:,}\nUnique: {len(self.bot.users):,}\n"\
                      f"Unique Members Online: {membertotal_online:,}"
        embed.add_field(name="Members", value=all_members)

        memory = self.process.memory_full_info().uss / 1024**2
        description.append(f"**Process**: {memory:.2f} MiB\n**Commit**: [{self.bot.commit_hash[:8]}]"
                           f"({embed.url}/commit/{self.bot.commit_hash})")

        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}\nShards: {self.bot.shard_count}")

        query = """SELECT COUNT(*) AS total_commands, (SELECT sum(count) FROM socket_stats) AS total_socket_stats
                   FROM commands_usage;"""
        amounts = await self.bot.pool.fetchrow(query)
        description.append(f"{amounts['total_commands']} commands ran.\n{amounts['total_socket_stats']} "
                           "socket events recorded.")

        embed.add_field(name="Links", value="[Support Server]"
                                            f"({self.bot.config['bot']['support_server_invite']}) | "
                                            "[Website](https://lightning.lightsage.dev) | [Ko-Fi]"
                                            "(https://ko-fi.com/lightsage)",
                                            inline=False)
        embed.set_footer(text=f"Lightning v{self.bot.version} | Made with "
                              f"discord.py {discord.__version__}")

        embed.description = '\n'.join(description)

        await ctx.send(embed=embed)

    @lcommand(name='copyright', aliases=['license'])
    async def _copyright(self, ctx: LightningContext) -> None:
        """Tells you about the copyright license for the bot"""
        await ctx.send("AGPLv3: https://gitlab.com/lightning-bot/Lightning/-/blob/master/LICENSE")

    @lcommand()
    async def donate(self, ctx: LightningContext) -> None:
        """Gives you a link to my donation page"""
        await ctx.send("**__Ko-Fi__**: <https://ko-fi.com/lightsage>")

    @lcommand(aliases=['prefixes'])
    async def prefix(self, ctx: LightningContext) -> None:
        """Shows prefixes the bot is listening for"""
        pfxs = await self.bot.get_prefix(ctx.message)
        pfxs = list(pfxs)
        del pfxs[0]
        embed = discord.Embed(title="Prefixes I am listening for",
                              description="\n".join(f"\"{p}\"" for p in pfxs),
                              color=discord.Color(0xf74b06))
        await ctx.send(embed=embed)

    @lcommand(aliases=['invite'])
    async def join(self, ctx: LightningContext, *ids: discord.Object) -> None:
        """Gives you a link to add the bot to your server or generates an invite link for a client id."""
        perms = discord.Permissions.none()

        if not ids:
            perms.kick_members = True
            perms.ban_members = True
            perms.manage_channels = True
            perms.add_reactions = True
            perms.view_audit_log = True
            perms.attach_files = True
            perms.manage_messages = True
            perms.external_emojis = True
            perms.manage_nicknames = True
            perms.manage_emojis = True
            perms.manage_roles = True
            perms.read_messages = True
            perms.send_messages = True
            perms.read_message_history = True
            perms.manage_webhooks = True
            perms.embed_links = True
            perms.manage_threads = True
            perms.moderate_members = True
            msg = "You can use this link to invite me to your server. (Select permissions as needed) "\
                  f"<{discord.utils.oauth_url(self.bot.user.id, permissions=perms)}>"
        else:
            msg = "\n".join("<{}>".format(discord.utils.oauth_url(o.id, permissions=perms)) for o in ids)

        await ctx.send(msg)

    @lcommand()
    async def support(self, ctx: LightningContext) -> None:
        """Sends an invite that goes to the support server"""
        await ctx.send("You can join this server to get support for this bot: "
                       f"{self.bot.config['bot']['support_server_invite']}")

    @lcommand()
    async def source(self, ctx: LightningContext, *, command: str = None) -> None:
        """Gives a link to the source code for a command."""
        source = self.bot.config['bot'].get("git_repo_url", "https://gitlab.com/lightning-bot/Lightning")
        if command is None:
            await ctx.send(source)
            return

        if command == "help":
            src = type(self.bot.help_command)
            module = src.__module__
            filename = inspect.getsourcefile(src)
        else:
            obj = self.bot.get_command(command.replace(".", " "))
            if obj is None:
                await ctx.send("I could not find that command.")
                return
            src = obj.callback.__code__
            module = obj.callback.__module__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        location = ""

        if module.startswith("jishaku"):
            location = module.replace(".", "/") + ".py"
            source = "https://github.com/Gorialis/jishaku"
            await ctx.send(f"<{source}/blob/master/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>")
            return

        if not module.startswith("discord"):
            location = os.path.relpath(filename).replace("\\", "/")

        await ctx.send(f"<{source}/blob/master/{location}#L{firstlineno}-{firstlineno + len(lines) - 1}>")

    async def show_channel_permissions(self, channel: discord.TextChannel, member, ctx: LightningContext) -> None:
        perms = channel.permissions_for(member)
        embed = discord.Embed(title="Channel Permissions", color=member.color)
        allowed = []
        denied = []
        for name, value in perms:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)
        if allowed:
            embed.add_field(name='Allowed', value='\n'.join(allowed))
        if denied:
            embed.add_field(name='Denied', value='\n'.join(denied))
        await ctx.send(embed=embed)

    @lcommand()
    async def permissions(self, ctx: LightningContext, member: discord.Member = commands.default.Author,
                          channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Shows channel permissions for a member"""
        await self.show_channel_permissions(channel, member, ctx)

    @lcommand()
    async def ping(self, ctx: LightningContext) -> None:
        """Tells you the ping."""
        if ctx.guild:
            shard_id = ctx.guild.shard_id
        else:
            shard_id = 0

        shard_latency = round(self.bot.get_shard(shard_id).latency * 1000)

        before = time.monotonic()
        tmpmsg = await ctx.send('Calculating...')
        after = time.monotonic()
        rtt_ms = round((after - before) * 1000)

        await tmpmsg.edit(content=f"Pong!\nshard {shard_id}: `{shard_latency} ms`\nrtt: `{rtt_ms} ms`")

    @lcommand()
    async def uptime(self, ctx: LightningContext) -> None:
        """Displays my uptime"""
        await ctx.send(f"Uptime: **{natural_timedelta(self.bot.launch_time, accuracy=None, suffix=False)}**")

    @commands.guild_only()
    @lcommand(aliases=['guildinfo'], usage='')
    async def serverinfo(self, ctx: LightningContext, guild: discord.Guild = commands.default.CurrentGuild) -> None:
        """Shows information about the server"""
        if await self.bot.is_owner(ctx.author):
            guild = guild
        else:
            guild = ctx.guild

        embed = discord.Embed(title=guild.name)
        embed.description = f"**ID**: {guild.id}\n**Owner**: {str(guild.owner)}"

        embed.add_field(name="Creation", value=f"{discord.utils.format_dt(guild.created_at)} "
                        f"({natural_timedelta(guild.created_at, accuracy=3)})", inline=False)

        if guild.icon:
            if guild.icon.is_animated():
                icon_url = guild.icon.with_format("gif")
            else:
                icon_url = guild.icon.with_static_format("png")
            embed.description += f"\n**Icon**: [Link]({icon_url})"

            embed.set_thumbnail(url=icon_url)

        member_by_status = collections.Counter()
        for m in guild.members:
            member_by_status[str(m.status)] += 1
            if m.bot:
                member_by_status["bots"] += 1
        fmt = f'{helpers.Emoji.online} {member_by_status["online"]} ' \
              f'{helpers.Emoji.idle} {member_by_status["idle"]} ' \
              f'{helpers.Emoji.do_not_disturb} {member_by_status["dnd"]} ' \
              f'{helpers.Emoji.offline}{member_by_status["offline"]}\n' \
              f'<:bot_tag:596576775555776522> {member_by_status["bots"]}\n'\
              f'Total: {guild.member_count}'
        embed.add_field(name="Members", value=fmt, inline=False)

        features = {"VIP_REGIONS": "VIP Voice Servers",
                    "DISCOVERABLE": "Server Discovery",
                    "PARTNERED": "Partnered",
                    "VERIFIED": "Verified",
                    "COMMUNITY": "Community Server",
                    "WELCOME_SCREEN_ENABLED": "Welcome Screen",
                    "INVITE_SPLASH": "Invite Splash",
                    "ANIMATED_ICON": "Animated Server Icon",
                    "BANNER": "Banner",
                    "VANITY_URL": "Vanity Invite URL",
                    "NEWS": "News Channels",
                    "MEMBER_VERIFICATION_GATE_ENABLED": "Membership Screening",
                    "THREADS_ENABLED": "Threads",
                    "PRIVATE_THREADS": "Private Threads",
                    "ROLE_ICONS": "Role Icons"}
        guild_features = []
        for key, value in features.items():
            if key in guild.features:
                guild_features.append(value)
        if guild_features:
            embed.add_field(name="Features",
                            value=', '.join(guild_features),
                            inline=False)

        if guild.premium_subscription_count:
            boosts = f"Tier: {guild.premium_tier}\n"\
                     f"{guild.premium_subscription_count} boosts."
            embed.add_field(name="Server Boost", value=boosts)

        await ctx.send(embed=embed)

    def message_info_embed(self, msg: discord.Message) -> discord.Embed:
        embed = discord.Embed(timestamp=msg.created_at)

        if hasattr(msg.author, 'nick') and msg.author.display_name != str(msg.author):
            author_name = f"{msg.author.display_name} ({msg.author})"
        else:
            author_name = msg.author

        embed.set_author(name=author_name, icon_url=msg.author.display_avatar.url)

        if msg.guild:
            embed.set_footer(text=f"\N{NUMBER SIGN}{msg.channel}")
        else:
            embed.set_footer(text=msg.channel)

        description = msg.content
        if msg.attachments:
            attach_urls = []
            for attachment in msg.attachments:
                attach_urls.append(f'[{attachment.filename}]({attachment.url})')
            description += '\n\N{BULLET} ' + '\n\N{BULLET} '.join(attach_urls)
        description += f"\n\n[Jump to message]({msg.jump_url})"
        if msg.embeds:
            description += "\n \N{BULLET} Message has an embed"
        embed.description = description

        if hasattr(msg.author, 'color'):
            embed.color = msg.author.color

        return embed

    @lgroup(aliases=['messageinfo', 'msgtext'], invoke_without_command=True)
    async def quote(self, ctx: LightningContext, *message) -> None:
        """Quotes a message"""
        message_id, channel = await Message().convert(ctx, message)
        msg = discord.utils.get(ctx.bot.cached_messages, id=message_id)
        if msg is None:
            try:
                msg = await helpers.message_id_lookup(ctx.bot, channel.id, message_id)
            except discord.NotFound:
                raise MessageNotFoundInChannel(message_id, channel)
            except discord.Forbidden:
                raise ChannelPermissionFailure(f"I don't have permission to view {channel.mention}.")
        else:
            await ReadableChannel().convert(ctx, str(msg.channel.id))

        embed = self.message_info_embed(msg)
        await ctx.send(embed=embed)

    @quote.command(name="raw", aliases=['json'])
    async def msg_raw(self, ctx: LightningContext, *message) -> None:
        """Shows raw JSON for a message."""
        message_id, channel = await Message().convert(ctx, message)
        try:
            message = await ctx.bot.http.get_message(channel.id, message_id)
        except discord.NotFound:
            raise MessageNotFoundInChannel(message_id, channel)

        await ctx.send(f"```json\n{json.dumps(message, indent=2, sort_keys=True)}```")


def setup(bot: LightningBot):
    bot.add_cog(Meta(bot))
    # Remove support command if not in config
    if bot.config['bot'].get("support_server_invite", None) is None:
        bot.remove_command("support")
