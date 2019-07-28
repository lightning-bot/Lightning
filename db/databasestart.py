# kirigiri - A discord bot.
# Copyright (C) 2018 - Valentijn "noirscape" V.
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
# In addition, the additional clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version; or
from database import StaffRoles, BlacklistGuild, Config, Roles, BlacklistUser, AutoRoles, Base
from discord.ext.commands import Cog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class BotDB:
    pass

# Changes to this adds the ability to create tables for any tables that aren't made.
def setup(bot):
    bot.db = BotDB()
    engine = create_engine('sqlite:///config/database.sqlite3')
    bot.db.dbsession = sessionmaker(bind=engine)
    Base.metadata.bind = engine
    Base.metadata.create_all(engine, tables=[StaffRoles.__table__, BlacklistGuild.__table__, 
                                             Roles.__table__, Config.__table__, 
                                             BlacklistUser.__table__, AutoRoles.__table__])
    print(f'Database successfully loaded')

