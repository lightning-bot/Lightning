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

class AutoRoles(Base):
    __tablename__ = "autoroles"
    # Must always have a value
    guild_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, primary_key=True)

class TagsTable(Base):
    __tablename__ = "tags"
    guild_id = Column(Integer, primary_key=True)
    tag_name = Column(String, primary_key=True)
    tag_content = Column(String, primary_key=True)
    tag_owner = Column(Integer, primary_key=True)
    tag_uses = Column(Integer, primary_key=True)
    tag_created = Column(DateTime, primary_key=True)

class TagAlias(Base):
    __tablename__ = "tag_aliases"
    guild_id = Column(Integer, primary_key=True)
    tag_name = Column(String, ForeignKey('tags.tag_name'))
    tag_alias = Column(String, primary_key=True)
    tag_owner = Column(Integer, primary_key=True)
    tag_created = Column(DateTime, primary_key=True)
    # Stupid Value Thing
    tag_is_alias = Column(String, primary_key=True)