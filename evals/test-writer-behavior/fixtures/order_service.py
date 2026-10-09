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
