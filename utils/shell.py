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
import subprocess


async def call_shell(shell_command: str):
    """Runs a command in the system's shell"""
    try:
        pipe = asyncio.subprocess.PIPE
        process = await asyncio.create_subprocess_shell(shell_command,
                                                        stdout=pipe,
                                                        stderr=pipe)
        stdout, stderr = await process.communicate()
    except NotImplementedError:
        process = subprocess.Popen(shell_command, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

    if stdout and stderr:
        return f"$ {shell_command}\n\n[stderr]\n"\
               f"{stderr.decode('utf-8')}===\n"\
               f"[stdout]\n{stdout.decode('utf-8')}"
    elif stdout:
        return f"$ {shell_command}\n\n"\
               f"[stdout]\n{stdout.decode('utf-8')}"
    elif stderr:
        return f"$ {shell_command}\n\n"\
               f"[stderr]\n{stderr.decode('utf-8')}"
