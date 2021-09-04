"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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

import asyncio
import inspect

import discord
from discord.ext import menus
from discord.ext.menus.views import ViewMenuPages


class BasicEmbedMenu(menus.ListPageSource):
    def __init__(self, data, *, per_page=4, embed=None):
        self.embed = embed
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, entries) -> discord.Embed:
        if self.embed:
            embed = self.embed
        else:
            embed = discord.Embed(color=discord.Color.greyple())
        embed.description = "\n".join(entries)
        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()}")
        return embed


class InfoMenuPages(ViewMenuPages):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @menus.button("\N{INFORMATION SOURCE}\ufe0f", position=menus.Last(3))
    async def info_page(self, payload) -> None:
        """shows you this message"""
        messages = ['Welcome to the interactive paginator!\n']
        messages.append('This interactively allows you to see pages of text by navigating with '
                        'reactions. They are as follows:\n')
        for emoji, button in self.buttons.items():
            messages.append(f'{str(emoji)} {button.action.__doc__}')

        embed = discord.Embed(color=discord.Color.blurple())
        embed.clear_fields()
        embed.description = '\n'.join(messages)
        embed.set_footer(text=f"We were on page {self.current_page + 1} before this message.")
        await self.message.edit(content=None, embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(60.0)
            await self.show_page(self.current_page)

        self.ctx.bot.loop.create_task(go_back_to_current_page())


class FieldMenus(menus.ListPageSource):
    def __init__(self, entries, *, per_page, **kwargs):
        super().__init__(entries, per_page=per_page)

    async def format_page(self, menu, entries) -> discord.Embed:
        embed = discord.Embed()
        for entry in entries:
            embed.add_field(name=entry[0], value=entry[1], inline=False)
        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()}")
        return embed


class Command:
    def __init__(self, check, action):
        self.check = check
        self.action = action

    # https://github.com/Rapptz/discord-ext-menus/blob/master/discord/ext/menus/__init__.py#L178-L198
    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        try:
            menu_self = value.__self__
        except AttributeError:
            pass
        else:
            # Unfurl the method to not be bound
            if not isinstance(menu_self, menus.Menu):
                raise TypeError('action bound method must be from Menu not %r' % menu_self)

            value = value.__func__

        if not inspect.iscoroutinefunction(value):
            raise TypeError('action must be a coroutine not %r' % value)

        self._action = value

    def __call__(self, menu, payload):
        return self.action(menu, payload)


class SessionMenu(menus.Menu):
    def __init__(self, *, timeout=180.0, delete_message_after=False, clear_reactions_after=False,
                 check_embeds=False, message=None, command=None):
        super().__init__(timeout=timeout, delete_message_after=delete_message_after,
                         clear_reactions_after=clear_reactions_after, check_embeds=check_embeds, message=message)
        self.command = command

    def add_command(self, check, func):
        self.command = Command(check, func)

    def message_check(self, payload):
        """Checks whether the payload should be processed"""
        if self.command is None:
            return False
        valid = self.command.check(payload)
        if valid is True:
            return True
        # failed all checks
        return False

    def reaction_check(self, payload):
        """The function that is used to check whether the payload should be processed.
        This is passed to :meth:`discord.ext.commands.Bot.wait_for <Bot.wait_for>`.

        There should be no reason to override this function for most users.

        Parameters
        ------------
        payload: :class:`discord.RawReactionActionEvent`
            The payload to check.

        Returns
        ---------
        :class:`bool`
            Whether the payload should be processed.
        """
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in {self.bot.owner_id, self._author_id, *self.bot.owner_ids}:
            return False

        return payload.emoji in self.buttons

    async def update(self, payload):
        if isinstance(payload, discord.Message):
            cmd = self.command.check(payload) if self.command else None
            if cmd:
                try:
                    await self.command(self, payload)
                except Exception:
                    import traceback
                    traceback.print_exc()
            return
        return await super().update(payload)

    async def _internal_loop(self):
        try:
            self.__timed_out = False
            loop = self.bot.loop
            # Ensure the name exists for the cancellation handling
            tasks = []
            while self._running:
                tasks = [
                    asyncio.ensure_future(self.bot.wait_for('raw_reaction_add', check=self.reaction_check)),
                    asyncio.ensure_future(self.bot.wait_for('raw_reaction_remove', check=self.reaction_check)),
                    asyncio.ensure_future(self.bot.wait_for('message', check=self.message_check))
                ]
                done, pending = await asyncio.wait(tasks, timeout=self.timeout, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()

                if len(done) == 0:
                    raise asyncio.TimeoutError()

                # Exception will propagate if e.g. cancelled or timed out
                payload = done.pop().result()
                loop.create_task(self.update(payload))

                # NOTE: Removing the reaction ourselves after it's been done when
                # mixed with the checks above is incredibly racy.
                # There is no guarantee when the MESSAGE_REACTION_REMOVE event will
                # be called, and chances are when it does happen it'll always be
                # after the remove_reaction HTTP call has returned back to the caller
                # which means that the stuff above will catch the reaction that we
                # just removed.

                # For the future sake of myself and to save myself the hours in the future
                # consider this my warning.

        except asyncio.TimeoutError:
            self.__timed_out = True
        finally:
            self._event.set()

            # Cancel any outstanding tasks (if any)
            for task in tasks:
                task.cancel()

            try:
                await self.finalize(self.__timed_out)
            except Exception:
                pass
            finally:
                self.__timed_out = False

            # Can't do any requests if the bot is closed
            if self.bot.is_closed():
                return

            # Wrap it in another block anyway just to ensure
            # nothing leaks out during clean-up
            try:
                if self.delete_message_after:
                    return await self.message.delete()

                if self.clear_reactions_after:
                    if self._can_remove_reactions:
                        return await self.message.clear_reactions()

                    for button_emoji in self.buttons:
                        try:
                            await self.message.remove_reaction(button_emoji, self.__me)
                        except discord.HTTPException:
                            continue
            except Exception:
                pass
