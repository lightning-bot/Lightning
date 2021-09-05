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
import contextlib
import logging
from inspect import isawaitable

import discord
import sentry_sdk

__all__ = ("BaseView",
           "MenuLikeView",
           "ExitableMenu",
           "UpdateableMenu",
           "SelectSubMenu",
           "ButtonSubMenu")
log = logging.getLogger(__name__)


class BaseView(discord.ui.View):
    """A view that adds cleanup and error logging to it"""
    async def cleanup(self):
        """Coroutine that cleans up something (like database connections, whatever).

        This is called either when the view has timed out or when the view has stopped."""
        pass

    async def on_timeout(self):
        await self.cleanup()

    def stop(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.cleanup())
        super().stop()

    async def on_error(self, error, item, interaction):
        with sentry_sdk.push_scope() as scope:
            # lines = traceback.format_exception(type(error), error, error.__traceback__, chain=False)
            # traceback_text = ''.join(lines)
            scope.set_extra("view", self)
            scope.set_extra("item", item)
            scope.set_extra("interaction", interaction)
            log.exception(f"An exception occurred during {self} with {item}", exc_info=error)


class MenuLikeView(BaseView):
    """A view that mimics similar behavior of discord.ext.menus.

    Parameters
    ----------
    clear_view_after : bool
        Whether to remove the view from the message after the view is done or timed out. Defaults to False
    delete_message_after : bool
        Whether to delete the message after the view is done or timed out. Defaults to False
    disable_components_after : bool
        Disables components after the view is done or has timed out.
        If the view has other components that cannot be disabled, like selects, they will be removed from the view.
        Defaults to True
    timeout : Optional[float]
        Defines when the view should stop listening for the interaction event."""
    def __init__(self, *, clear_view_after=False, delete_message_after=False, disable_components_after=True,
                 timeout=180.0):
        super().__init__(timeout=timeout)
        self.locked = False
        self.ctx = None
        self.clear_view_after = clear_view_after
        self.delete_message_after = delete_message_after
        self.disable_components_after = disable_components_after

    # Seemed like reasonable naming
    def format_initial_message(self, ctx):
        """Formats the initial message to send with when starting the menu via the start method.

        This can be sync or async."""
        raise NotImplementedError

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        check = self.ctx.author.id == interaction.user.id
        if self.locked is True and check is True:
            await interaction.response.defer()
            await interaction.followup.send(content="You have not finished a prompt yet", ephemeral=True)
            return False
        else:
            return check

    def _assume_message_kwargs(self, value) -> dict:  # "Assumes" kwargs that are passed to message.send
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': value, 'embed': None}
        elif isinstance(value, discord.Embed):
            return {'embed': value, 'content': None}

    async def start(self, ctx, *, channel=None, wait=True) -> None:
        self.ctx = ctx

        dest = channel or ctx.channel

        fmt = self.format_initial_message(ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        self.message = await dest.send(**kwargs, view=self)

        if wait:
            await self.wait()

    def lock_components(self) -> None:
        self.locked = True

    def unlock_components(self) -> None:
        self.locked = False

    @contextlib.contextmanager
    def sub_menu(self, view):
        """Context manager for submenus.

        Parameters
        ----------
        view
            A view. Ideally, this should be SelectSubMenu or ButtonSubMenu.
        """
        # There might need to be more involvement, but this is simple atm.
        view.ctx = self.ctx
        try:
            yield view
        finally:
            pass

    async def cleanup(self) -> None:
        # This is first for obvious reasons
        if self.delete_message_after:
            await self.message.delete()
            return

        if self.clear_view_after:
            await self.message.edit(view=None)
            return

        if self.disable_components_after:
            for child in self.children:
                if hasattr(child, "disabled"):
                    child.disabled = True
                else:
                    self.remove_item(child)
            await self.message.edit(view=self)


class StopButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.stop()


class ExitableMenu(MenuLikeView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.add_item(StopButton(label="Exit"))


class UpdateableMenu(MenuLikeView):
    async def update(self) -> None:
        await self.update_components()

        fmt = self.format_initial_message(self.ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        await self.message.edit(**kwargs, view=self)

    async def update_components(self) -> None:
        ...

    @contextlib.asynccontextmanager
    async def sub_menu(self, view):
        """Async context manager for submenus.

        Parameters
        ----------
        view
            A view. Ideally, this should be SelectSubMenu or ButtonSubMenu.
        """
        view.ctx = self.ctx
        self.lock_components()
        try:
            # await interaction.response.defer()
            # message = await interaction.followup.send(view=view, wait=True)
            yield view
        finally:
            self.unlock_components()
            await self.update()

    async def start(self, ctx, *, channel=None, wait=True) -> None:
        self.ctx = ctx

        dest = channel or ctx.channel

        await self.update_components()

        fmt = self.format_initial_message(ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        self.message = await dest.send(**kwargs, view=self)

        if wait:
            await self.wait()


# classes for easy-to-use submenus!
class _SelectSM(discord.ui.Select):
    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.stop()


class SelectSubMenu(BaseView):
    """
    A view designed to work for submenus.

    To retrieve the values after the view has stopped, use the values attribute.
    """
    def __init__(self, *options, max_options: int = 1, exitable: bool = True, **kwargs):
        super().__init__(**kwargs)
        select = _SelectSM(max_values=max_options)

        for option in options:
            if isinstance(option, discord.ui.Select):
                select.append_option(option)
            else:
                select.add_option(label=option)

        self.add_item(select)

        if exitable:
            stop_buttton = StopButton(label="Exit")
            self.add_item(stop_buttton)

        self._select = select

    @property
    def values(self):
        return self._select.values or []


class _ButtonSM(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.stop()
        self.view.result = self.label


class ButtonSubMenu(BaseView):
    """
    A view designed to work for submenus.

    To retrieve the button that was pressed, use the result attribute.

    Parameters
    ----------
    *choices : tuple(str)
        Choices to choose from.
    style : discord.ButtonStyle
        A style to use for the buttons. Defaults to discord.ButtonStyle.primary.
    """
    def __init__(self, *choices, style: discord.ButtonStyle = discord.ButtonStyle.primary):
        super().__init__()
        self.result = None

        for x in choices:
            self.add_item(_ButtonSM(label=x, style=style))
