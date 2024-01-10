"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from __future__ import annotations

from typing import Any, Dict


class CratesIOResponse:
    __slots__ = ('crates', 'total', 'previous_page', 'next_page')

    def __init__(self, data: Dict[str, Any]):
        self.crates = [Crate(x) for x in data['crates']]
        self.total = data['meta']['total']
        self.previous_page = data['meta']['prev_page']
        self.next_page = data['meta']['next_page']


class Crate:
    __slots__ = ('id', 'name', 'description', 'downloads', 'homepage', 'documentation', 'repository',
                 'exact_match', 'newest_version', 'max_version')

    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self.name = data['name']
        self.description = data['description'].strip()
        self.downloads = data['downloads']
        self.homepage = data['homepage']
        self.documentation = data['documentation']
        self.repository = data['repository']
        self.exact_match = data['exact_match']

        self.newest_version = data['newest_version']
        self.max_version = data['max_version']

    def __repr__(self):
        return f"<Crate id={self.id}>"
