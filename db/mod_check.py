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
from discord.ext import commands
import discord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import StaffRoles


DATABASE_URI = 'sqlite:///config/database.sqlite3'


def __start_session():
    engine = create_engine(DATABASE_URI)
    sessionmake = sessionmaker(bind=engine)
    session = sessionmake()
    return engine, sessionmake, session


def __close_session(session, sessionmake, engine):
    session.close()
    sessionmake.close_all()
    engine.dispose()


def check_if_at_least_has_staff_role(min_role: str):
    """
    Checks and verifies if a user has the needed staff level

    min_role is either admin, mod or helper.

    Quick overview of what to grant to whom (permissions are incremental):
    - Helper: User nicknames, warnings.
    - Moderator: Kicking and banning users.
    - Admin: Server management.
    """
    def predicate(ctx):
        return member_at_least_has_staff_role(ctx.author, min_role)

    return commands.check(predicate)

def is_staff_and_has_perms(min_role: str, **perms):
    """
    Checks and verifies if a user has the needed staff level or permission
    """
    def predicate(ctx):
        if member_at_least_has_staff_role(ctx.author, min_role):
            return True
        permissions = ctx.author.guild_permissions
        return all(getattr(permissions, perms, None) == value for perms, value in perms.items())

    return commands.check(predicate)

def is_role_staff_role(role):
    """Check if role is a staff role"""
    engine, sessionmake, session = __start_session()
    try:
        session.query(StaffRoles).filter_by(role_id=role.id).one()
    except:
        __close_session(session, sessionmake, engine)
        return False
    else:
        __close_session(session, sessionmake, engine)
        return True


def get_all_staff_roles_for_guild(guild):
    staff_roles = []

    engine, sessionmake, session = __start_session()
    for role in session.query(StaffRoles).filter_by(guild_id=guild.id):
        staff_roles.append(discord.utils.get(guild.roles, id=role.role_id))
    __close_session(session, sessionmake, engine)
    return staff_roles


def member_at_least_has_staff_role(member: discord.Member, min_role: str="Helper"):
    """
    Non-check function for check_if_at_least_has_staff_role()
    """
    if not hasattr(member, 'roles'):
        return False
    role_list = ["helper", "moderator", "admin"]
    for role in role_list.copy():
        if role_list.index(role) < role_list.index(min_role.lower()):
            role_list.remove(role)

    engine, sessionmake, session = __start_session()

    staff_roles = []
    for role in role_list:
        try:
            for q in session.query(StaffRoles).filter_by(guild_id=member.guild.id, staff_perms=role).all():
                staff_roles.append(q.role_id)
        except:
            pass

    __close_session(session, sessionmake, engine)

    user_roles = [role.id for role in member.roles]
    if any(role in user_roles for role in staff_roles):
        return True
    else:
        return False


def get_staff_role(rank, guild):
    engine, sessionmake, session = __start_session()
    try:
        role = session.query(StaffRoles).filter_by(guild_id=guild.id, staff_perms=rank.lower()).one()

        # Dumb thing since theres no role converter
        role = discord.utils.get(guild.roles, id=role.role_id)
    except:
        role = None
    __close_session(session, sessionmake, engine)
    return role
