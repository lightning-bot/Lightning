# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import asyncio
import contextlib
import logging
import logging.handlers
import os
import sys

import discord
import toml

from lightning import LightningBot

try:
    import uvloop
except ImportError:
    # Lol get fucked windows
    pass
else:
    uvloop.install()


@contextlib.contextmanager
def init_logging():
    try:
        max_file_size = 1000 * 1000 * 8
        file_handler = logging.handlers.RotatingFileHandler(filename="lightning.log", maxBytes=max_file_size,
                                                            backupCount=10)
        log_format = logging.Formatter('[%(asctime)s] %(name)s (%(filename)s:%(lineno)d) %(levelname)s: %(message)s')
        file_handler.setFormatter(log_format)

        log = logging.getLogger()
        log.setLevel(logging.INFO)
        log.addHandler(file_handler)

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(log_format)
        log.addHandler(stdout_handler)
        yield
    finally:
        logging.shutdown()


def launch_bot() -> None:
    loop = asyncio.get_event_loop()

    # Create config folder if not found
    if not os.path.exists("config"):
        os.makedirs("config")

    config = toml.load(open("config.toml", "r"))
    log = logging.getLogger("lightning")

    bot = LightningBot()

    if config['bot']['game']:
        bot.activity = discord.Game(config['bot']['game'])

    try:
        loop.run_until_complete(bot.create_pool(config, command_timeout=60))
    except Exception as e:
        log.exception(f"Could not set up PostgreSQL. {e}\n----\nExiting...")
        return

    bot.run(config['tokens']['discord'])


def main() -> None:
    with init_logging():
        launch_bot()


main()
