import sqlite3
from pathlib import Path

def seed(database):
    with sqlite3.connect(database) as connection:
        connection.executescript(Path(__file__).with_name("schema.sql").read_text())

def status(database, order_id=101):
    # Fresh connection/transaction to observe committed state.
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()[0]
