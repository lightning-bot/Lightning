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
import asyncio
import contextlib
import logging
import logging.handlers
import os
import sys

import discord
import migri
import sentry_sdk
import typer

from lightning.bot import LightningBot
from lightning.cli import guild, tools
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
parser.add_typer(tools.parser, name="tools", help="Developer tools")
parser.add_typer(guild.parser, name="guild", help="Guild management commands")


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
        sentry_sdk.init(sentry_dsn, environment=env, release=commit)

    bot_config = config._storage.get('bot', {})

    message_cache = bot_config.get('message_cache', 1000)
    kwargs = {'max_messages': message_cache}

    owner_ids = bot_config.get('owner_ids', None)
    if owner_ids:
        kwargs['owner_ids'] = owner_ids

    game = bot_config.get("game", None)
    if game:
        kwargs['activity'] = discord.Game(game)

    bot = LightningBot(**kwargs)
    bot.commit_hash = commit

    # idk but adding your own cogs to your own instance might be useful(?)
    # ~~Feels like this is becoming another Red bot.~~
    # This should be a list of extra cogs you want to add. e.g. ['ext.publisher', 'ext.emojify']
    extra_cogs = bot_config.get("extra_cogs", None)
    if extra_cogs:
        for cog in extra_cogs:
            bot.load_extension(cog)

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


@parser.command(hidden=True)
def docker_run():
    typer.echo("Applying migrations...")

    loop = asyncio.get_event_loop()

    pg_uri = CONFIG['tokens']['postgres']['uri']

    async def migrate():
        pool = await create_pool(pg_uri, command_timeout=60)
        async with pool.acquire() as conn:
            m = migri.PostgreSQLConnection(connection=conn)
            await migri.apply_migrations("migrations", m)
    loop.run_until_complete(migrate())

    with init_logging():
        launch_bot(CONFIG)


if __name__ == "__main__":
    parser()
