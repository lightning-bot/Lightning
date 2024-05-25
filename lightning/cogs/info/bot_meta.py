"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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

import inspect
import os
from typing import Optional

import discord

from lightning import LightningCog, LightningContext, command, hybrid_command


class BotMeta(LightningCog):
    @command(name='copyright', aliases=['license'])
    async def _copyright(self, ctx: LightningContext) -> None:
        """Tells you about the copyright license for the bot"""
        await ctx.send("AGPLv3: https://github.com/lightning-bot/Lightning/blob/master/LICENSE")

    @command()
    async def donate(self, ctx: LightningContext) -> None:
        """Gives you a link to my donation page"""
        await ctx.send("**__Ko-Fi__**: <https://ko-fi.com/lightsage>")

    @command()
    async def support(self, ctx: LightningContext) -> None:
        """Sends an invite that goes to the support server"""
        await ctx.send("You can join this server to get support for this bot: "
                       f"{self.bot.config.bot.support_server_invite}")

    @command(aliases=['invite'])
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
            perms.send_messages_in_threads = True
            perms.manage_webhooks = True
            perms.embed_links = True
            perms.manage_threads = True
            perms.moderate_members = True
            msg = "You can use this link to invite me to your server. (Select permissions as needed) "\
                  f"<{discord.utils.oauth_url(self.bot.user.id, permissions=perms)}>"
        else:
            msg = "\n".join(f"<{discord.utils.oauth_url(o.id, permissions=perms)}>" for o in ids)

        await ctx.send(msg)

    @command(aliases=['prefixes'])
    async def prefix(self, ctx: LightningContext) -> None:
        """Shows prefixes the bot is listening for"""
        pfxs = await self.bot.get_prefix(ctx.message)
        pfxs = list(pfxs)
        del pfxs[0]
        embed = discord.Embed(title="Prefixes I am listening for",
                              description="\n".join(f"\"{p}\"" for p in pfxs),
                              color=discord.Color(0xf74b06))
        await ctx.send(embed=embed)

    @hybrid_command()
    async def source(self, ctx: LightningContext, *, command: Optional[str] = None) -> None:
        """Gives a link to the source code for a command."""
        source = self.bot.config['bot'].get("git_repo_url", "https://github.com/lightning-bot/Lightning")
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

    @LightningCog.listener('on_lightning_guild_add')
    async def send_guild_onboarding_message(self, guild: discord.Guild):
        msg = (f"Thanks for adding me to your server! By default, my prefix is {self.bot.user.mention}, "
               "but that can be changed! "
               "To add a custom prefix, run @Lightning config prefix\n\n"
               "To get a list of my commands, you can run the `help` command. For information about an individual"
               " command, you can use `help [command]`"
               "\n\n*If you need any help setting up this bot, please visit the support server at "
               f"{self.bot.config.bot.support_server_invite} and someone will help!\nYou can additionally "
               "visit <https://lightning.lightsage.dev/> for documentation to set up some of the bot's features!*")

        default_channel = guild.system_channel
        if default_channel and default_channel.permissions_for(guild.me).send_messages is True:
            await default_channel.send(msg)
            return

        notice_channel = guild.public_updates_channel
        if notice_channel and notice_channel.permissions_for(guild.me).send_messages is True:
            await notice_channel.send(msg)
