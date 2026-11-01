---
description: Test writer respects ownership, supplied fixtures and real rollback evidence
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Ask fastapi-test-writer to propose pytest tests for the supplied service in a FastAPI project.
The HTTP adapter is deliberately not supplied. Keep production code unchanged.
Cover success, missing order, wrong-owner denial and rollback after the first write.
Observe committed state with a separate transaction. Reuse the supplied fixtures.
The JSON file is the existing HTTP error contract; do not invent a new envelope.

### Fixture: fixtures/fixture_data.py

```python
import sqlite3
from pathlib import Path

def seed(database):
    with sqlite3.connect(database) as connection:
        connection.executescript(Path(__file__).with_name("schema.sql").read_text())

def status(database, order_id=101):
    # Fresh connection/transaction to observe committed state.
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()[0]
```

### Fixture: fixtures/order_service.py

```python
import sqlite3

class OrderAccessDenied(Exception):
    pass

class OrderService:
    def __init__(self, database):
        self.database = database

    def approve(self, order_id, actor, event_id):
        with sqlite3.connect(self.database) as connection:
            order = connection.execute("SELECT owner FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order is None:
                raise LookupError(order_id)
            if order[0] != actor:
                raise OrderAccessDenied("You cannot access this order")
            connection.execute("UPDATE orders SET status = 'APPROVED' WHERE id = ?", (order_id,))
            connection.execute("INSERT INTO events (order_id, event_id) VALUES (?, ?)", (order_id, event_id))
```

### Fixture: fixtures/ownership-error.json

```json
{"status":403,"code":"ORDER_ACCESS_DENIED","message":"You cannot access this order","path":"/orders/101/approve"}
```

### Fixture: fixtures/schema.sql

```sql
CREATE TABLE orders (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE events (order_id INTEGER NOT NULL, event_id TEXT NOT NULL CHECK (event_id <> 'FAIL_DB'));
INSERT INTO orders VALUES (101, 'alice', 'PENDING');
```
