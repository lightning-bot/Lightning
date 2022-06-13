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
from lightning import flags

BaseModParser = flags.FlagParser([flags.Flag("--nodm", "--no-dm", is_bool_flag=True,
                                             help="Bot does not DM the user the reason for the action."),
                                  flags.Flag(attribute="reason", consume_rest=True)],
                                 raise_on_bad_flag=False)
