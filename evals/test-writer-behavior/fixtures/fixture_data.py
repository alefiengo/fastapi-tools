from contextlib import closing
import sqlite3
from pathlib import Path

def seed(database):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executescript(Path(__file__).with_name("schema.sql").read_text())

def status(database, order_id=101):
    # Fresh connection/transaction to observe committed state.
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()[0]
