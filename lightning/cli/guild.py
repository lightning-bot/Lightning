"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
import asyncpg
import typer

from lightning.cli.utils import asyncd
from lightning.config import Config

parser = typer.Typer()
tables = [("commands_usage", "guild_id"), ("nin_updates", "guild_id"), ("guilds", "id"),
          ("guild_config", "guild_id"), ("guild_mod_config", "guild_id"), ("roles", "guild_id"),
          ("logging", "guild_id"), ("infractions", "guild_id")]


def build_delete_query(table: str, column: str) -> str:
    query = f"DELETE FROM {table} WHERE {column}=$1"
    return query


@parser.command()
@asyncd
async def cleardata(id: int = typer.Argument(...),
                    prompt: bool = typer.Option(True, help="Whether to ask before removing data from a table")):
    """Clears all data for a guild in the database."""
    cfg = Config()
    pool = await asyncpg.create_pool(cfg['tokens']['postgres']['uri'])
    for table in tables:
        if prompt:
            resp = typer.confirm(f"Are you sure you want to remove data from {table[0]}?")
            if resp:
                await pool.execute(build_delete_query(*table), id)
            else:
                continue
        else:
            await pool.execute(build_delete_query(*table), id)

    typer.echo("Done")


if __name__ == "__main__":
    parser()
