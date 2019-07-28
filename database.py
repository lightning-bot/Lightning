from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()

class StaffRoles(Base):
    __tablename__ = "staff_roles"
    guild_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, primary_key=True)
    staff_perms = Column(String, primary_key=True)

class BlacklistGuild(Base):
    __tablename__ = "blacklist_guild"
    guild_id = Column(Integer, primary_key=True)

class Roles(Base):
    __tablename__ = "roles"
    guild_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, primary_key=True)

class Config(Base):
    __tablename__ = "guild_configuration"
    guild_id = Column(Integer, primary_key=True)
    mute_role_id = Column(Integer)

class BlacklistUser(Base):
    __tablename__ = "blacklisted_users"
    user_id = Column(Integer, primary_key=True)
    reason = Column(String)

class AutoRoles(Base):
    __tablename__ = "autoroles"
    # Must always have a value
    guild_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, primary_key=True)