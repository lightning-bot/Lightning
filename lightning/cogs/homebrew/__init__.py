from __future__ import annotations

from typing import TYPE_CHECKING

from .cog import Homebrew

if TYPE_CHECKING:
    from lightning import LightningBot


def setup(bot: LightningBot) -> None:
    bot.add_cog(Homebrew(bot))
