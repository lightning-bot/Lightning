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

import logging
from typing import TYPE_CHECKING, List, Optional, Union

import discord
from discord.ext import commands, menus
from rapidfuzz.process import extractOne

from lightning import LightningCog
from lightning.commands import LightningCommand, LightningGroupCommand
from lightning.context import LightningContext
from lightning.utils.paginator import Paginator

if TYPE_CHECKING:
    from lightning import LightningBot

log = logging.getLogger(__name__)
flag_name_lookup = {"HumanTime": "Time", "FutureTime": "Time"}


def format_commands(commands: Union[LightningCommand, LightningGroupCommand]):
    cmds = []
    for cmd in commands:
        cmds.append(f"\N{BULLET} `{cmd.qualified_name}`\n")
        if hasattr(cmd, 'commands'):
            cmds.extend(f'{" " * (len(child.parents) * 3)}• `{child.qualified_name}`\n'
                        for child in cmd.walk_commands())

    return "".join(cmds)


class HelpPaginator(Paginator):
    def __init__(self, help_command: PaginatedHelpCommand, ctx: LightningContext, source, **kwargs):
        super().__init__(source, **kwargs)
        self.help_command = help_command
        self.total = len(source.entries)
        self.ctx = ctx
        self.bot = ctx.bot
        self.is_bot = False

    @discord.ui.button(label="How to read bot signature", emoji="\N{WHITE QUESTION MARK ORNAMENT}", row=2,
                       style=discord.ButtonStyle.blurple)
    async def show_bot_help(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
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

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(self, menu: HelpPaginator, *, options: List[discord.SelectOption] = ...,
                 row: Optional[int] = None) -> None:
        super().__init__(placeholder="Jump to category", options=options, row=row)
        self.menu = menu
        # We don't display command signature so this button seems kinda extra
        self.menu.remove_item(self.menu.show_bot_help)

    async def callback(self, interaction: discord.Interaction):
        # self.placeholder = self.menu.source.entries[int(self.values[0])]
        await self.menu.show_page(interaction, int(self.values[0]))


class BotHelpSource(menus.ListPageSource):
    def __init__(self, entries):
        data = sorted(entries.keys())
        self.data = entries
        super().__init__(data, per_page=1)

    async def format_page(self, menu: HelpPaginator, entry) -> discord.Embed:
        description = f"Use \"{menu.ctx.clean_prefix}help [command]\" for help about a command.\nYou can also use \""\
                      f"{menu.ctx.clean_prefix}help [category]\" for help about a category."
        if "support_server_invite" in menu.bot.config['bot']:
            description += "\nFor additional help, join the support server: "\
                           f"<{menu.bot.config['bot']['support_server_invite']}>"

        cmds = sorted(self.data.get(entry, []), key=lambda d: d.qualified_name)
        value = f"**{entry}**\n{f'*{cmds[0].cog.description}*' if cmds[0].cog.description else ''}"\
                f"\nYour current permissions allow you to run the following commands:\n{format_commands(cmds)}"

        return f"{value}\n{description}"


class CogHelpSource(menus.ListPageSource):
    def __init__(self, data, *, per_page=5):
        self.total = len(data)
        super().__init__(data, per_page=per_page)

    def format_signature(self, command):
        return f" {command.signature}" if command.signature else ""

    async def format_page(self, menu: HelpPaginator, entries) -> discord.Embed:
        cmds = [f"\N{BULLET} `{command.qualified_name}{self.format_signature(command)}` ("
                f"{command.short_doc or 'No help found...'})\n" for command in entries]

        content = f"**{entries[0].cog.qualified_name}**\n*{entries[0].cog.description}*\n"\
                  f"Your current permissions allow you to run the following commands:\n{''.join(cmds)}\n\n"\
                  f"*Use \"{menu.ctx.clean_prefix}help [command]\" for help about a command.*"\
                  f"\nPage {menu.current_page + 1} of {self.get_max_pages() or 1}"
        return content


class GroupHelpSource(CogHelpSource):
    def __init__(self, data, *, per_page=7, group=None):
        self.group = group
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu: HelpPaginator, entries) -> discord.Embed:
        if menu.current_page == 0 and await self.group.can_run(menu.ctx):
            content = f"Your current permissions allow you to run the following group command:\n"\
                      f"{menu.help_command.common_command_formatting(self.group)}"
        else:
            content = f"Your current permissions do not allow you to run the following group command:\n"\
                      f"{menu.help_command.common_command_formatting(self.group)}"

        cmds = [f"\N{BULLET} `{command.qualified_name}{self.format_signature(command)}` ("
                f"{command.short_doc or 'No help found...'})\n" for command in entries]

        content += f"\n\n**Subcommands**:\nYour current permissions allow you to run the following subcommands:\n"\
                   f"{''.join(cmds)}\n\n"\
                   f"*Use \"{menu.ctx.clean_prefix}help [command]\" for help about a command.*"\
                   f"\nPage {menu.current_page + 1} of {self.get_max_pages() or 1}"
        return content


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

        menu = HelpPaginator(self, self.context, BotHelpSource(commands))

        options = [discord.SelectOption(label=key, value=ix) for ix, key in enumerate(sorted(commands.keys()))]
        menu.add_item(CategorySelect(menu, options=options, row=3))

        await menu.start(self.context)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        entries = await self.filter_commands(cog.walk_commands(), sort=True, key=lambda d: d.qualified_name)
        menu = HelpPaginator(self, self.context, CogHelpSource(entries, per_page=10))
        await menu.start(self.context)

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

    def common_command_formatting(self, command: Union[LightningCommand, LightningGroupCommand]):
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

        if cflags := self.flag_help_formatting(command):
            fmt = "\n".join(cflags)
            desc.append(f'\n\n{fmt}')

        if hasattr(command, 'level'):
            desc.append(f"\n\n**Default Level Required**: {command.level.name}")

        channel, guild = self.permissions_required_format(command)
        if channel:
            req = ", ".join(channel).replace('_', ' ').replace('guild', 'server').title()
            desc.append(f"\n**Channel Permissions Required**: {req}")
        if guild:
            req = ", ".join(guild).replace('_', ' ').replace('guild', 'server').title()
            desc.append(f"\n**Server Permissions Required**: {req}")

        return ''.join(desc)

    async def send_command_help(self, command: LightningCommand):
        # No pagination necessary for a single command.
        if await command.can_run(self.context):
            content = "Your current permissions allow you to run this command.\n"\
                      f"{self.common_command_formatting(command)}"
        else:
            content = "Your current permissions do not allow you to run this command!\n"\
                      f"{self.common_command_formatting(command)}"
        await self.context.send(content)

    async def send_group_help(self, group: LightningGroupCommand):
        entries = await self.filter_commands(group.walk_commands(), sort=True, key=lambda c: c.qualified_name)
        pages = HelpPaginator(self, self.context, GroupHelpSource(entries, group=group))
        await pages.start(self.context)


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
