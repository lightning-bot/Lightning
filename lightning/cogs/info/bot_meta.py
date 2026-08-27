"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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
import logging
import os
from datetime import timedelta
from typing import Optional

import discord

from lightning import LightningCog, LightningContext, command, hybrid_command

log = logging.getLogger(__name__)


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
        msg = ("⚡ **Thanks for adding Lightning!** I can help keep this server safe from raids, spam, and "
               "rule-breakers, with clean, easy to follow mod logs, in just a couple minutes.\n\n"
               "**Get protected right now:**\n"
               "\N{BULLET} Run `/automod rules interactive` for a guided walkthrough that sets up AutoMod "
               "rules for spam and raid protection\n"
               "\N{BULLET} Run `/modlog` in the channel you want moderation actions logged to\n\n"
               f"By default, my prefix is {self.bot.user.mention}, but that can be changed with "
               "`config prefix`. You can also run `help` for a full list of commands.\n\n"
               "*Need a hand? Visit the support server at "
               f"{self.bot.config.bot.support_server_invite}, or check out the "
               "AutoMod quick-start guide below.*")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.grey,
                                        label="AutoMod Quick Start",
                                        url="https://lightning.lightsage.dev/guide/automod-configuration"))
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.grey,
                                        label="Documentation",
                                        url="https://lightning.lightsage.dev/"))

        if not await self.attempt_onboarding_send(guild, msg, view):
            # No suitable channel was available (or we lacked permissions), so fall back to DMing the
            # owner rather than silently dropping the onboarding message.
            status = "dm" if await self.attempt_onboarding_dm(guild, msg, view) else "failed"
        else:
            status = "channel"

        await self.record_onboarding_delivery(guild, status)

    async def attempt_onboarding_send(self, guild: discord.Guild, msg: str, view: discord.ui.View) -> bool:
        for channel in (guild.system_channel, guild.public_updates_channel):
            if channel and channel.permissions_for(guild.me).send_messages is True:
                try:
                    await channel.send(msg, view=view)
                except discord.HTTPException:
                    log.warning(f"Failed to send onboarding message in guild {guild.name} ({guild.id})")
                    continue
                return True

        return False

    async def attempt_onboarding_dm(self, guild: discord.Guild, msg: str, view: discord.ui.View) -> bool:
        owner = guild.owner
        if owner is None and guild.owner_id is not None:
            try:
                owner = await self.bot.fetch_user(guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is None:
            log.warning("Could not find a channel or owner to send the onboarding message to for guild "
                        f"{guild.name} ({guild.id})")
            return False

        try:
            preamble = "*(This server has no channel I could post in, so here's a heads up instead!)*\n\n"
            await owner.send(preamble + msg, view=view)
        except discord.Forbidden:
            log.warning(f"Could not deliver the onboarding message for guild {guild.name} ({guild.id}) "
                        "via channel or DM.")
            return False
        except discord.HTTPException:
            log.warning(f"Failed to DM the owner of guild {guild.name} ({guild.id}) with the onboarding message.")
            return False

        return True

    async def record_onboarding_delivery(self, guild: discord.Guild, status: str) -> None:
        # Tracks whether the onboarding message actually reached someone, so delivery gaps (e.g. no
        # available channel and an undeliverable DM) are visible instead of silently failing.
        try:
            await self.bot.redis_pool.set(f"lightning:onboarding-sent:{guild.id}", value=status,
                                          ex=timedelta(days=30))
        except Exception:
            log.warning(f"Failed to record onboarding delivery status for guild {guild.name} ({guild.id})")
