"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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
import typing

import toml


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
        with open(self.file_name, 'w') as fp:
            json.dump(self._storage.copy(), fp, ensure_ascii=True, separators=(',', ':'))

    async def save(self) -> None:
        async with self.lock:
            await self.loop.run_in_executor(None, self._dump)

    def get(self, key: str) -> typing.Any:
        """Gets an entry in storage.

        Parameters
        ----------
        key : str
            The key to get from storage

        Returns
        -------
        typing.Optional[typing.Union[str, int]]
            The value of the key
        """
        return self._storage.get(str(key))

    async def add(self, key: str, value: typing.Any) -> None:
        """Adds a new entry in the storage and saves.

        Parameters
        ----------
        key : str
            The key to add
        value
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
        dict
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


class TOMLStorage(Storage):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_file(self):
        with open(self.file_name) as f:
            self._storage = toml.load(f)

    def _dump(self):
        with open(self.file_name, 'w') as r:
            toml.dump(self._storage.copy(), r)

    async def append(self, key, value):
        if not isinstance(key, list):
            raise ValueError("key must be a list")
        key.append(value)
        await self.save()
