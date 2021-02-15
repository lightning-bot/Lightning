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
# from lightning.errors import ConfigTableMissing
from lightning.storage import TOMLStorage


class Base(TOMLStorage):
    def __init__(self, file_path: str = 'config.toml'):
        super().__init__(file_path)


CONFIG = Base()
