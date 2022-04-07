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
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, menus
from rapidfuzz.process import extractOne

from lightning import LightningCog
from lightning.utils.paginator import InfoMenuPages

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

        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages() or 1} ({self.total or 1} "
                              "categories)", icon_url=menu.ctx.bot.user.avatar.url)
        return embed

    def format_group_embed(self, embed: discord.Embed, menu, entries: list) -> discord.Embed:
        for command in entries:
            signature = f"{command.qualified_name} {command.signature}"
            embed.add_field(name=signature, value=command.short_doc or "No help found...", inline=False)

        embed.set_author(name=f"Page {menu.current_page + 1} of {self.get_max_pages() or 1} ({self.total or 1} "
                              "commands)", icon_url=menu.ctx.bot.user.avatar.url)
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

    async def send_bot_help(self, _) -> None:
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


class Help(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot
        self.original_help_command = bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.original_help_command


async def setup(bot: LightningBot):
    await bot.add_cog(Help(bot))
