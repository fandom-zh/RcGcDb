import sqlite3
from src.config import settings

db_connection = sqlite3.connect(settings.get("database_path", 'rcgcdb.db'))
db_cursor = db_connection.cursor()
