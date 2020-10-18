"""
Lightning.py - A personal Discord bot
Copyright (C) 2020 - LightSage

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

from dataclasses import dataclass, field
from typing import List

from discord.ext import commands

from lightning.bot import LightningBot


@dataclass
class LightningCogDeps:
    required: List[str] = field(default_factory=list)


class LightningCog(commands.Cog):
    def __init__(self, bot: LightningBot):
        self.bot = bot

    def __init_subclass__(cls, *args, **kwargs):
        required_cogs = kwargs.get("required", [])
        cls.__lightning_cog_deps__ = LightningCogDeps(required=required_cogs)

    def __str__(self):
        """Returns the cog’s specified name, not the class name."""
        return self.qualified_name
