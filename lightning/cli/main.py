"""
Lightning.py - A personal Discord bot
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
import logging.handlers
import os
import sys

import discord
import sentry_sdk
import typer
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from lightning.bot import LightningBot
from lightning.cli.utils import asyncd
from lightning.config import CONFIG
from lightning.utils.helpers import create_pool, run_in_shell

try:
    import uvloop
except ImportError:
    # Lol get fucked windows
    pass
else:
    uvloop.install()


parser = typer.Typer()


@contextlib.contextmanager
def init_logging():
    try:
        max_file_size = 1000 * 1000 * 8
        file_handler = logging.handlers.RotatingFileHandler(filename="lightning.log", maxBytes=max_file_size,
                                                            backupCount=10)
        log_format = logging.Formatter('[%(asctime)s] %(name)s (%(filename)s:%(lineno)d) %(levelname)s: %(message)s')
        file_handler.setFormatter(log_format)

        logging_config = CONFIG.get("logging") or {}

        log = logging.getLogger()

        if (level := logging_config.get("level", "INFO")) != "":
            log.setLevel(level)
        else:
            log.setLevel("INFO")

        log.addHandler(file_handler)

        console_handler = logging_config.get("console", True)

        if console_handler:
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(log_format)
            log.addHandler(stdout_handler)

        yield
    finally:
        logging.shutdown()


def launch_bot(config) -> None:
    loop = asyncio.get_event_loop()

    # Create config folder if not found
    if not os.path.exists("config"):
        os.makedirs("config")

    log = logging.getLogger("lightning")

    sentry_dsn = config._storage.get('tokens', {}).get("sentry", None)
    commit = (loop.run_until_complete(run_in_shell('git rev-parse HEAD')))[0].strip()

    if sentry_dsn is not None:
        env = "dev" if "beta_prefix" in config['bot'] else "prod"
        sentry_sdk.init(sentry_dsn, integrations=[AioHttpIntegration()], environment=env, release=commit)

    bot = LightningBot()
    bot.commit_hash = commit
    if config['bot']['game']:
        bot.activity = discord.Game(config['bot']['game'])

    try:
        bot.pool = loop.run_until_complete(create_pool(config['tokens']['postgres']['uri'], command_timeout=60))
    except Exception as e:
        log.exception("Could not set up PostgreSQL. Exiting...", exc_info=e)
        return

    bot.run(config['tokens']['discord'])


@parser.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        with init_logging():
            launch_bot(CONFIG)


@parser.command(help="Initializes the database")
@asyncd
async def init_db(init_yoyo: bool = typer.Option(False, "--setup-migrations",
                                                 help="Initializes the yoyo.ini file for migrations")):
    typer.echo("Running initial schema script...")

    pg_uri = CONFIG['tokens']['postgres']['uri']
    pool = await create_pool(pg_uri, command_timeout=60)
    with open("scripts/schema.sql", "r") as fp:
        await pool.execute(fp.read())

    if init_yoyo is True:
        typer.echo("Setting up migrations config file...")
        import configparser
        cfg = configparser.ConfigParser()
        cfg['DEFAULT'] = {"sources": "migrations/",
                          "migration_table": "_yoyo_migration",
                          "batch_mode": "off",
                          "verbosity": 0,
                          "database": pg_uri}
        cfg.write(open('yoyo.ini', 'w'))
        typer.echo("Created migrations config file")

    typer.echo("Done!")


if __name__ == "__main__":
    parser()
