from sqlalchemy import create_engine
import database
from config import database_connection

def makedb():
    print("Connecting to PostgreSQL.....")
    engine = create_engine(database_connection)
    database.Base.metadata.bind = engine
    tables_list = [database.StaffRoles.__table__, database.BlacklistGuild.__table__, 
    database.Roles.__table__, database.Config.__table__,
    database.AutoRoles.__table__, database.TagsTable.__table__, database.TagAlias.__table__]
    print("Creating tables.....")
    database.Base.metadata.create_all(engine, tables=tables_list)


if __name__ == '__main__':
    makedb()