"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, TypedDict

import asyncpg
import typer

from lightning.cli.utils import asyncd
from lightning.config import Config

if TYPE_CHECKING:
    class MigratoryConfig(TypedDict):
        postgres_uri: str
        applied: List[str]


class Revision:
    def __init__(self, file: Path) -> None:
        self.file = file

    async def forward(self, conn: asyncpg.Connection):
        sql = self.file.read_text("utf-8")
        await conn.execute(sql)

    def __str__(self) -> str:
        return str(self.file)


class PYRevision(Revision):
    """A .py revision file"""
    def __init__(self, file: Path) -> None:
        super().__init__(file)
        spec = importlib.util.spec_from_file_location(str(file), file)

        if not spec:
            raise Exception("Missing spec")

        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    async def forward(self, conn: asyncpg.Connection):
        await self.module.start(conn)


class Migrator:
    """The main class for Migratory."""
    __slots__ = ("root", "revisions", "config")

    def __init__(self) -> None:
        self.root = Path("migrations")
        self.revisions = self.load_migrations()
        self.config = self.load_config()

    def load_migrations(self):
        fps: List[Revision] = []
        for file in self.root.glob("*.sql"):
            fps.append(Revision(file))

        for file in self.root.glob("*.py"):
            fps.append(PYRevision(file))
        return fps

    @property
    def sorted_revisions(self):
        return sorted(self.revisions, key=lambda x: str(x.file))

    def load_config(self) -> MigratoryConfig:
        try:
            with open(self.root / "migratory.json", mode="r", encoding="utf-8") as fp:
                return json.load(fp)
        except FileNotFoundError:
            cfg = Config()
            return {"postgres_uri": cfg.tokens.postgres.uri, "applied": []}

    def save(self):
        with open(self.root / "migratory.json", mode="w", encoding="utf-8") as fp:
            json.dump(self.config, fp)

    async def apply_revisions(self, conn: asyncpg.Connection):
        revisions = self.sorted_revisions
        applied: List[Revision] = []
        async with conn.transaction():
            for revision in revisions:
                if str(revision) in self.config['applied']:
                    continue

                await revision.forward(conn)
                typer.secho(f"Applied {str(revision)}!", fg=typer.colors.GREEN)
                applied.append(revision)

        self.config['applied'].extend([str(a) for a in applied])
        self.save()

        return applied

    def display_pending_revisions(self):
        for rev in self.sorted_revisions:
            if rev in self.config['applied']:
                continue
            sql = rev.file.read_text("utf-8")
            typer.echo(f"{str(rev)}\n{sql}")


parser = typer.Typer(name='db', help="Database migration commands")


@parser.command()
@asyncd
async def upgrade(sql: Optional[bool] = typer.Option(False,
                                                     help="Displays the SQL that would be applied", is_flag=True)):
    """Applies all pending migrations"""
    m = Migrator()

    if sql:
        m.display_pending_revisions()
        return

    try:
        conn = await asyncpg.connect(m.config["postgres_uri"])
    except Exception as e:
        typer.echo(f"Unable to connect to the database!\n{e}")
        return

    applied = await m.apply_revisions(conn)
    await conn.close()
    typer.echo(f"Applied {len(applied)} migrations!")


@parser.command(name='log')
@asyncd
async def display_log():
    """Displays what migrations are pending and are applied"""
    m = Migrator()

    for rev in m.sorted_revisions:
        if str(rev) in m.config['applied']:
            style = typer.style("Applied", fg='green')
        else:
            style = typer.style("Pending", fg='red')

        typer.echo(f"{style} {str(rev)}")


@parser.command('reset')
@asyncd
async def reset_migrations():
    """Resets your applied migrations list"""
    m = Migrator()

    if m.config["applied"] == []:
        typer.echo("No migrations have been applied yet!")
        return

    m.config["applied"] = []
    m.save()
    typer.echo("Reset your migrations config")
