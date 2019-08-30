# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

from config import database_connection
#import click
from lightning import LightningBot
import asyncio
import config

try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

def startbot():
    loop = asyncio.get_event_loop()
    bot = LightningBot()
    try:
        bot.db = loop.run_until_complete(bot.create_pool(config.database_connection, 
                                                         command_timeout=60))
    except Exception as e:
        print(f"Could not set up PostgreSQL. {e}\n----\nExiting...")
        return
    bot.run(config.token, bot=True, reconnect=True)

if __name__ == '__main__':
    startbot()