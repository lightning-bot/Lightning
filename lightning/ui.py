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

import asyncio
import contextlib
import functools
import logging
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import discord
import sentry_sdk

if TYPE_CHECKING:
    from lightning import LightningContext

__all__ = ("BaseView",
           "lock_when_pressed",
           "BasicMenuLikeView",
           "MenuLikeView",
           "ExitableMenu",
           "UpdateableLayoutView",
           "UpdateableMenu",
           "SelectSubMenu",
           "ButtonSubMenu")
log = logging.getLogger(__name__)


class _BaseView(discord.ui.view.BaseView):
    """A view that adds cleanup and error logging to it"""
    async def cleanup(self):
        """Coroutine that cleans up something (like database connections, whatever).

        This is called either when the view has timed out or when the view has stopped."""
        pass

    async def on_timeout(self):
        await self.cleanup()

    def stop(self):
        asyncio.create_task(self.cleanup())
        super().stop()

    async def on_error(self, interaction, error, item):
        with sentry_sdk.push_scope() as scope:  # type: ignore
            # lines = traceback.format_exception(type(error), error, error.__traceback__, chain=False)
            # traceback_text = ''.join(lines)
            scope.set_extra("view", self)
            scope.set_extra("item", item)
            scope.set_extra("interaction", interaction)
            log.exception(f"An exception occurred during {self} with {item}", exc_info=error)


class BaseView(_BaseView, discord.ui.View):
    ...


class AuthorLockedBaseView(_BaseView):
    """Basic view that handles basic locking, cleanup logic, and interaction_check"""
    def __init__(self, author_id: int, *, timeout: float | None = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.locked = False

    async def on_timeout(self):
        self.stop()

    def stop(self, *, interaction: Optional[discord.Interaction] = None):
        asyncio.create_task(self.cleanup(interaction=interaction))
        super().stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        check = self.author_id == interaction.user.id
        if self.locked is True and check is True:
            await interaction.response.defer()
            await interaction.followup.send(content="You have not finished a prompt yet", ephemeral=True)
            return False
        else:
            return check

    async def cleanup(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        ...

    def lock_components(self) -> None:
        self.locked = True

    def unlock_components(self) -> None:
        self.locked = False


def lock_when_pressed(func):
    @functools.wraps(func)
    async def wrapper(self: MenuLikeView, interaction: discord.Interaction, component):
        async with self.lock(interaction=interaction):
            await func(self, interaction, component)

    return wrapper


class BasicMenuLikeView(AuthorLockedBaseView, discord.ui.View):
    """A view that mimics similar behavior of discord.ext.menus. This is a simpler version of MenuLikeView

    Parameters
    ----------
    author_id : int
        The ID of the author who started this menu (used for interaction checks)
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
    def __init__(self, *, author_id: int, clear_view_after=False, delete_message_after=False,
                 disable_components_after=True, timeout: Optional[float] = 180.0):
        super().__init__(author_id, timeout=timeout)
        self.clear_view_after = clear_view_after
        self.delete_message_after = delete_message_after
        self.disable_components_after = disable_components_after

    # Seemed like reasonable naming
    def format_initial_message(self, ctx: LightningContext):
        """Formats the initial message to send with when starting the menu via the start method.

        This can be sync or async."""
        raise NotImplementedError

    def _assume_message_kwargs(self, value: Union[Dict[str, Any], str, discord.Embed]) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': value}
        elif isinstance(value, discord.Embed):
            return {'embed': value}

    async def start(self, ctx: LightningContext, *, wait=True) -> None:
        fmt = self.format_initial_message(ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        self.message = await ctx.send(**kwargs, view=self)

        if wait:
            await self.wait()

    @classmethod
    def from_interaction(cls, interaction: discord.Interaction, **kwargs):
        return cls(author_id=interaction.user.id, **kwargs)

    @contextlib.contextmanager
    def sub_menu(self, view):
        """Context manager for submenus.

        Parameters
        ----------
        view
            A view. Ideally, this should be SelectSubMenu or ButtonSubMenu.
        """
        try:
            yield view
        finally:
            pass

    @contextlib.asynccontextmanager
    async def lock(self, **kwargs):
        self.lock_components()
        try:
            yield
        finally:
            self.unlock_components()

    async def cleanup(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        # This is first for obvious reasons
        if self.delete_message_after:
            if interaction:
                if interaction.response.is_done() is False:
                    await interaction.response.defer()
                await interaction.delete_original_response()
            elif hasattr(self, 'message'):
                await self.message.delete()
            return

        if self.clear_view_after:
            if interaction and interaction.response.is_done() is False:
                await interaction.response.edit_message(view=None)
                return

            if hasattr(self, 'message'):
                await self.message.edit(view=None)
            return

        if self.disable_components_after:
            for child in self.children:
                if hasattr(child, "disabled"):
                    child.disabled = True  # type: ignore
                else:
                    self.remove_item(child)

            if interaction and interaction.response.is_done() is False:
                await interaction.response.edit_message(view=self)
                return

            if hasattr(self, 'message'):
                await self.message.edit(view=self)

    async def on_error(self, interaction, error, item):
        with sentry_sdk.push_scope() as scope:  # type: ignore
            scope.set_extra("view", self)
            scope.set_extra("item", item)
            scope.set_extra("interaction", interaction)
            log.exception(f"An exception occurred during {self} with {item}", exc_info=error)


class MenuLikeView(discord.ui.View):
    """A view that mimics similar behavior of discord.ext.menus.

    Parameters
    ----------
    context : LightningContext
        The context for this menu
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
    def __init__(self, *, context: LightningContext, clear_view_after=False, delete_message_after=False,
                 disable_components_after=True, timeout=180.0):
        super().__init__(timeout=timeout)
        self.ctx = context
        self.locked = False
        self.clear_view_after = clear_view_after
        self.delete_message_after = delete_message_after
        self.disable_components_after = disable_components_after

    # Seemed like reasonable naming
    def format_initial_message(self, ctx: LightningContext):
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

    def _assume_message_kwargs(self, value: Union[Dict[str, Any], str, discord.Embed]) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': value}
        elif isinstance(value, discord.Embed):
            return {'embed': value}

    async def start(self, *, wait=True) -> None:
        fmt = self.format_initial_message(self.ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        self.message = await self.ctx.send(**kwargs, view=self)

        if wait:
            await self.wait()

    @classmethod
    async def from_interaction(cls, interaction: discord.Interaction, **kwargs):
        from .context import LightningContext

        ctx = await LightningContext.from_interaction(interaction)
        return cls(context=ctx, **kwargs)

    async def on_timeout(self):
        self.stop()

    def stop(self, *, interaction: Optional[discord.Interaction] = None):
        asyncio.create_task(self.cleanup(interaction=interaction))
        super().stop()

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

    @contextlib.asynccontextmanager
    async def lock(self, **kwargs):
        self.lock_components()
        try:
            yield
        finally:
            self.unlock_components()

    async def prompt_convert(self, interaction: discord.Interaction, content: str, converter: Any) -> Optional[Any]:
        pmsg = await interaction.followup.send(content=content, wait=True)

        def check(m):
            return m.channel == self.ctx.channel and m.author == self.ctx.author

        try:
            message = await self.ctx.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send(content="Timed out while waiting for a response from you.", ephemeral=True)

            with contextlib.suppress(discord.HTTPException):
                await pmsg.delete()

            return

        try:
            conv = await converter.convert(self.ctx, message.content)
        except Exception as e:
            conv = None
            await interaction.followup.send(content=str(e), ephemeral=True)

        with contextlib.suppress(discord.HTTPException):
            await pmsg.delete()
            await message.delete()

        return conv

    async def cleanup(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        # This is first for obvious reasons
        if self.delete_message_after:
            if interaction:
                if interaction.response.is_done() is False:
                    await interaction.response.defer()
                await interaction.delete_original_response()
            elif hasattr(self, 'message'):
                await self.message.delete()
            return

        if self.clear_view_after:
            if interaction and interaction.response.is_done() is False:
                await interaction.response.edit_message(view=None)
                return

            if hasattr(self, 'message'):
                await self.message.edit(view=None)
            return

        if self.disable_components_after:
            for child in self.children:
                if hasattr(child, "disabled"):
                    child.disabled = True  # type: ignore
                else:
                    self.remove_item(child)

            if interaction and interaction.response.is_done() is False:
                await interaction.response.edit_message(view=self)
                return

            if hasattr(self, 'message'):
                await self.message.edit(view=self)

    async def on_error(self, interaction, error, item):
        with sentry_sdk.push_scope() as scope:  # type: ignore
            scope.set_extra("view", self)
            scope.set_extra("item", item)
            scope.set_extra("interaction", interaction)
            log.exception(f"An exception occurred during {self} with {item}", exc_info=error)


class UpdateableLayoutView(AuthorLockedBaseView, discord.ui.LayoutView):
    def __init__(self, *, context: LightningContext, delete_message_after=False,
                 disable_components_after=True, timeout=180.0):
        super().__init__(context.author.id, timeout=timeout)
        self.ctx = context
        self.delete_message_after = delete_message_after
        self.disable_components_after = disable_components_after

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

    @contextlib.asynccontextmanager
    async def lock(self, *, interaction: Optional[discord.Interaction] = None):
        self.lock_components()
        try:
            yield
        finally:
            self.unlock_components()

            await self.update(interaction=interaction)

    async def start(self, *, wait: bool = True):
        await self.update_components()

        self.message = await self.ctx.send(view=self)

        if wait:
            await self.wait()

    async def update(self, *, interaction: Optional[discord.Interaction] = None):
        await self.update_components()

        if interaction and interaction.response.is_done() is False:
            await interaction.response.edit_message(view=self)
            return

        await self.message.edit(view=self)

    async def update_components(self) -> None:
        ...

    async def cleanup(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        # This is first for obvious reasons
        if self.delete_message_after:
            if interaction:
                if interaction.response.is_done() is False:
                    await interaction.response.defer()
                await interaction.delete_original_response()
            elif hasattr(self, 'message'):
                await self.message.delete()
            return

        if self.disable_components_after:
            for child in self.walk_children():
                if hasattr(child, "disabled"):
                    child.disabled = True  # type: ignore
                # We don't remove children cause they could be TextDisplays and such like we do in UpdateableMenu

            if interaction and interaction.response.is_done() is False:
                await interaction.response.edit_message(view=self)
                return

            if hasattr(self, 'message'):
                await self.message.edit(view=self)


class StopButton(discord.ui.Button['MenuLikeView']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.stop(interaction=interaction)


class ExitableMenu(MenuLikeView):
    def __init__(self, *, context: LightningContext, clear_view_after=False, delete_message_after=False,
                 disable_components_after=True, timeout=180):
        super().__init__(context=context, clear_view_after=clear_view_after,
                         delete_message_after=delete_message_after, disable_components_after=disable_components_after,
                         timeout=timeout)

        self.add_item(StopButton(label="Exit"))


class UpdateableMenu(MenuLikeView):
    async def update(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        await self.update_components()

        fmt = self.format_initial_message(self.ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)

        if interaction and interaction.response.is_done() is False:
            await interaction.response.edit_message(**kwargs, view=self)
            return

        await self.message.edit(**kwargs, view=self)

    async def update_components(self) -> None:
        ...

    @contextlib.asynccontextmanager
    async def sub_menu(self, view: discord.ui.View, *, interaction: Optional[discord.Interaction] = None):
        """Async context manager for submenus. This assigns the ctx variable to the view and locks the components

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
            await self.update(interaction=interaction)

    @contextlib.asynccontextmanager
    async def lock(self, *, interaction: Optional[discord.Interaction] = None):
        self.lock_components()
        try:
            yield
        finally:
            self.unlock_components()

            await self.update(interaction=interaction)

    async def start(self, *, wait=True) -> None:
        await self.update_components()

        fmt = self.format_initial_message(self.ctx)
        if isawaitable(fmt):
            fmt = await fmt

        kwargs = self._assume_message_kwargs(fmt)
        self.message = await self.ctx.send(**kwargs, view=self)

        if wait:
            await self.wait()


# classes for easy-to-use submenus!
class _SelectSM(discord.ui.Select['SelectSubMenu']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None

        await interaction.response.defer()

        self.view.stop(interaction=interaction)


class SelectSubMenu(MenuLikeView):
    """
    A view designed to work for submenus.

    To retrieve the values after the view has stopped, use the values attribute.
    """
    def __init__(self, *options: Union[str, discord.SelectOption], max_options: int = 1, exitable: bool = True,
                 **kwargs):
        super().__init__(**kwargs)
        select = _SelectSM(max_values=max_options)

        for option in options:
            if isinstance(option, discord.SelectOption):
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

    async def cleanup(self, *, interaction: Optional[discord.Interaction] = None) -> None:
        return


class _ButtonSM(discord.ui.Button['ButtonSubMenu']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None

        self.view.stop(interaction=interaction)
        self.view.result = self.label


class ButtonSubMenu(MenuLikeView):
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
    def __init__(self, *choices, context: LightningContext, style: discord.ButtonStyle = discord.ButtonStyle.primary):
        super().__init__(context=context)
        self.result: Optional[str] = None

        for x in choices:
            self.add_item(_ButtonSM(label=x, style=style))
