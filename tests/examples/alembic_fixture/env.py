"""Isolated executable migration environment; never imports a user's app."""
from alembic import context
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

metadata = MetaData()
Table('products', metadata, Column('id', Integer, primary_key=True), Column('name', String(100)))

engine = create_engine(context.config.get_main_option('sqlalchemy.url'))
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
