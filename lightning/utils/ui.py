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
import discord

from lightning.ui import MenuLikeView
from lightning.utils.helpers import Emoji


class ConfirmationView(MenuLikeView):
    """A confirmation view.

    This is similar to ConfirmationMenu, except it uses discord bot kit ui instead.

    Parameters
    ----------
    message : str
        The message to send
    timeout : float
        When the view should time out
    include_help_message : bool
        Whether to include a help message in the message sent
    **kwargs
        Kwargs that are passed to MenuLikeView

    Returns
    -------
    Optional[bool]
        ``True`` if explicit confirm,
        ``False`` if explicit deny,
        ``None`` if deny due to timeout
    """

    def __init__(self, message: str, *, timeout=60.0, include_help_message: bool = False, **kwargs):
        super().__init__(timeout=timeout, **kwargs)
        self.msg = message
        self.include_help_message = include_help_message
        self.value = None

    def format_initial_message(self, ctx) -> str:
        if self.include_help_message:
            return self.msg + "\n\nPress the buttons below to respond."
        else:
            return self.msg

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green, emoji=Emoji.greentick)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        self.value = True
        self.stop()

    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red, emoji=Emoji.redtick)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        self.value = False
        self.stop()
