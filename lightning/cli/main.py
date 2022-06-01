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

import aioredis
import asyncpg
import discord
import sentry_sdk
import typer

from lightning.bot import LightningBot
from lightning.cli import guild, tools
from lightning.cli.utils import asyncd
from lightning.config import Config
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
def init_logging(config: Config):
    try:
        # Clear any existing loggers
        log = logging.getLogger()
        if log.hasHandlers():
            log.handlers.clear()

        max_file_size = 1000 * 1000 * 8
        file_handler = logging.handlers.RotatingFileHandler(filename="lightning.log", maxBytes=max_file_size,
                                                            backupCount=10)
        log_format = logging.Formatter('[%(asctime)s] %(name)s (%(filename)s:%(lineno)d) %(levelname)s: %(message)s')
        file_handler.setFormatter(log_format)

        if (level := config.logging.level) != "":
            log.setLevel(level)
        else:
            log.setLevel("INFO")

        log.addHandler(file_handler)

        if config.logging.console:
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(log_format)
            log.addHandler(stdout_handler)

        yield
    finally:
        logging.shutdown()


async def launch_bot(config: Config) -> None:
    # Create config folder if not found
    if not os.path.exists("config"):
        os.makedirs("config")

    log = logging.getLogger()

    sentry_dsn = config.tokens.sentry
    commit = (await run_in_shell('git rev-parse HEAD'))[0].strip()

    if sentry_dsn is not None:
        env = "dev" if config.bot.beta_prefix else "prod"
        sentry_sdk.init(sentry_dsn, environment=env, release=commit)

    kwargs = {'max_messages': config.bot.message_cache_max}

    if config.bot.owner_ids:
        kwargs['owner_ids'] = config.bot.owner_ids

    if config.bot.game:
        kwargs['activity'] = discord.Game(config.bot.game)

    bot = LightningBot(config, **kwargs)
    bot.commit_hash = commit

    try:
        bot.pool = await create_pool(bot.config['tokens']['postgres']['uri'], command_timeout=60)
        bot.redis_pool = aioredis.Redis(host=bot.config.tokens.redis.host, port=bot.config.tokens.redis.port,
                                        db=bot.config.tokens.redis.db, password=bot.config.tokens.redis.password)
        # Only way to ensure the pool is connected to redis
        await bot.redis_pool.ping()
    except asyncpg.PostgresConnectionError as e:
        log.exception("Could not set up PostgreSQL. Exiting...", exc_info=e)
        return
    except aioredis.ConnectionError as e:
        log.exception("Could not setup redis pool. Exiting...", exc_info=e)
        return

    await bot.start(config['tokens']['discord'])


@parser.callback(invoke_without_command=True)
@asyncd
async def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        config = Config()
        with init_logging(config):
            await launch_bot(config)


@parser.command(hidden=True)
@asyncd
async def docker_run():
    typer.echo("Applying migrations...")

    loop = asyncio.get_event_loop()
    config = Config()

    async def migrate():
        import migri

        pool = await create_pool(config.tokens.postgres.uri, command_timeout=60)
        async with pool.acquire() as conn:
            m = migri.PostgreSQLConnection(connection=conn)
            await migri.apply_migrations("migrations", m)

    loop.run_until_complete(migrate())

    with init_logging(config):
        await launch_bot(config)


if __name__ == "__main__":
    parser()
