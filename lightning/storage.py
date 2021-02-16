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
import json
import os
import secrets
import typing

from tomlkit import dumps as toml_dumps
from tomlkit import parse as toml_parse


# Storage.py (MIT Licensed) from https://gitlab.com/LightSage/python-bin/-/blob/master/storage.py
class Storage:
    def __init__(self, file_name: str, *, loop=None):

        self.file_name = file_name
        self.lock = asyncio.Lock()
        self.loop = loop if loop else asyncio.get_event_loop()
        self.load_file()

    def load_file(self) -> None:
        """Loads the file"""
        try:
            with open(self.file_name, 'r') as f:
                self._storage = json.load(f)
        except FileNotFoundError:
            self._storage = dict()

    def _dump(self) -> None:
        name = self.file_name.replace("/", "_")
        tmp = f"{secrets.token_hex()}-{name}.tmp"
        with open(tmp, 'w') as fp:
            json.dump(self._storage.copy(), fp, ensure_ascii=True, separators=(',', ':'))

        # atomicity
        os.replace(tmp, self.file_name)

    async def save(self) -> None:
        async with self.lock:
            await self.loop.run_in_executor(None, self._dump)

    def get(self, key: str) -> typing.Any:
        """Gets a key from storage.

        Parameters
        ----------
        key : str
            The key to get

        Returns
        -------
        typing.Any
            The value of the key
        """
        return self._storage.get(str(key))

    async def add(self, key: str, value: typing.Any) -> None:
        """Adds a new entry in the storage and saves.

        Parameters
        ----------
        key : str
            The key to add
        value : typing.Any
            The value to associate to the key
        """
        self._storage[str(key)] = value
        await self.save()

    async def pop(self, key: str) -> typing.Any:
        """Pops a storage key and saves.

        Parameters
        ----------
        key : str
            The key to pop from storage.

        Returns
        -------
        typing.Any
            The value of the key that was popped.
        """
        value = self._storage.pop(str(key))
        await self.save()
        return value

    def __contains__(self, item: str):
        return str(item) in self._storage

    def __getitem__(self, item: str):
        return self._storage[str(item)]

    def __len__(self):
        return len(self._storage)

    def __iter__(self):
        return iter(self._storage)


class TOMLStorage(Storage):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_file(self):
        with open(self.file_name) as f:
            self._storage = toml_parse(f.read())

    def _dump(self):
        name = self.file_name.replace("/", "_")
        tmp = f"{secrets.token_hex()}-{name}.tmp"
        with open(tmp, 'w') as r:
            r.write(toml_dumps(self._storage.copy()))

        os.replace(tmp, self.file_name)

    def __setitem__(self, key, value):
        self._storage.__setitem__(key, value)
