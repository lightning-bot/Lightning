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

import discord

__all__ = ("BaseView",
           "MenuLikeView")


class BaseView(discord.ui.View):
    """A view that adds cleanup to it"""
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


class MenuLikeView(BaseView):
    """A view that mimics similar behavior of discord.ext.menus.

    This is intended for use with discord.ui.buttons, but you can use discord.ui.select too.

    Parameters
    ----------
    clear_view_after : bool
        Whether to remove the view after the view is done or timed out. Defaults to True
    delete_message_after : bool
        Whether to delete the message after the view is done or timed out. Defaults to False
    timeout : Optional[float]
        Defines when the view should stop listening for the interaction event."""
    def __init__(self, *, clear_view_after=True, delete_message_after=False, timeout=180.0):
        super().__init__(timeout=timeout)
        self.ctx = None
        self.clear_view_after = clear_view_after
        self.delete_message_after = delete_message_after

    # Seemed like reasonable naming
    def format_initial_message(self, ctx):
        raise NotImplementedError

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id and \
            self.ctx.channel.id == interaction.channnel.id

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

        kwargs = self._assume_message_kwargs(self.format_initial_message(ctx))
        self.message = await dest.send(**kwargs, view=self)

        if wait:
            await self.wait()

    async def cleanup(self) -> None:
        # This is first for obvious reasons
        if self.delete_message_after:
            await self.message.delete()
            return

        if self.clear_view_after:
            await self.message.edit(view=None)
