import sqlite3
from pathlib import Path

from src.memory import create_tables


def connect(path: Path) -> sqlite3.Connection:
    # Pydantic AI runs tools in another thread, one at a time per connection.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # The conversation memory does not depend on the data load: a new database already supports it.
    create_tables(connection)
    return connection
