"""
Lightning.py - A Discord bot
Copyright (C) 2019-present Célveren

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

from dataclasses import dataclass
from typing import Callable, Generic, Literal, Type, TypeVar, Union

import discord

from lightning.formatters import format_timestamp

FormatName = Literal["emoji", "minimal", "embed"]


@dataclass(frozen=True)
class FormatContext:
    """How a guild wants its modlog entries to look.

    with_timestamp only means something to the minimal format, so it lives here
    instead of being a kwarg that the other two formats would have to ignore.
    """
    fmt: FormatName
    with_timestamp: bool = True

    @classmethod
    def from_setting(cls, setting: str) -> FormatContext:
        """Builds a context from the format string we store in the database"""
        if setting in ("minimal with timestamp", "minimal without timestamp"):
            return cls("minimal", setting != "minimal without timestamp")
        if setting not in ("emoji", "embed"):
            raise ValueError(f"Unknown modlog format: {setting}")
        return cls(setting)  # type: ignore


E = TypeVar("E")


class Renderer(Generic[E]):
    """Base class for a modlog renderer. Subclasses are registered with :func:`renders`.

    One renderer handles one kind of event, and knows how to show it in every format.
    """
    def __init__(self, event: E) -> None:
        self.event = event

    def mentions(self) -> list:
        """Who the emoji format is allowed to ping."""
        return []

    def emoji(self) -> str:
        raise NotImplementedError

    def minimal(self, ctx: FormatContext) -> str:
        raise NotImplementedError

    def embed(self) -> discord.Embed:
        raise NotImplementedError

    def stamp(self, ctx: FormatContext, when=None) -> str:
        """The "[time] " prefix that the minimal format puts at the front, if the guild wants it."""
        if not ctx.with_timestamp:
            return ""
        return f"[{format_timestamp(when or discord.utils.utcnow())}] "

    def render(self, ctx: FormatContext) -> Union[str, discord.Embed]:
        # This is the only spot that knows which format maps to which method
        if ctx.fmt == "emoji":
            return self.emoji()
        if ctx.fmt == "minimal":
            return self.minimal(ctx)
        return self.embed()


# Each renderer tags itself with @renders(SomeEvent) so there's no lookup table to keep up by hand,
# and the cog never has to know which renderers exist.
_renderers: dict[type, Type[Renderer]] = {}
_R = TypeVar("_R", bound=Type[Renderer])


def renders(event_type: type) -> Callable[[_R], _R]:
    def decorator(cls: _R) -> _R:
        _renderers[event_type] = cls
        return cls
    return decorator


def get_renderer(event) -> Renderer:
    """Finds the renderer for an event.

    We walk the MRO so a subclass of an event with a renderer (ex. LightningAutoModInfractionEvent)
    still works, but a renderer for the subclass itself (ex. MemberRolesUpdateEvent) wins.
    """
    for cls in type(event).__mro__:
        if cls in _renderers:
            return _renderers[cls](event)

    raise LookupError(f"No modlog renderer registered for {type(event).__name__}")
