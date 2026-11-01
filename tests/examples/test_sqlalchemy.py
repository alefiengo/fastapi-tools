"""Real ORM transactions and HTTP errors observed from independent sessions."""
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
import pytest
from sqlalchemy import CheckConstraint, ForeignKey, create_engine, func, select
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str]
    status: Mapped[str]


class Event(Base):
    __tablename__ = 'events'
    __table_args__ = (CheckConstraint("event_id <> 'FAIL_DB'", name='ck_event_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    event_id: Mapped[str]


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "orders.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Order(id=101, owner='alice', status='PENDING'))
    try:
        yield engine
    finally:
        engine.dispose()


def test_fastapi_ownership_failure_after_flush_and_public_orm_output(database):
    app = FastAPI()

    def actor():
        return 'bob'

    def get_session():
        with Session(database) as session:
            yield session

    @app.post('/orders/{order_id}/approve', response_model=OrderRead)
    def approve(order_id: int, event_id: str, current_actor: Annotated[str, Depends(actor)],
                session: Annotated[Session, Depends(get_session)]):
        try:
            with session.begin():
                order = session.get(Order, order_id)
                if order is None:
                    raise HTTPException(404, 'Order not found')
                if order.owner != current_actor:
                    raise HTTPException(403, 'Access denied')
                order.status = 'APPROVED'
                session.flush()  # Establish the first real UPDATE before failure.
                session.add(Event(order_id=order_id, event_id=event_id))
                session.flush()
                output = OrderRead.model_validate(order)
            return output
        except IntegrityError:
            raise HTTPException(409, 'Event rejected')

    def observe(expected_status, event_count):
        # No outer test transaction; this session sees committed database state.
        with Session(database) as observer:
            assert observer.get(Order, 101).status == expected_status
            assert observer.scalar(select(func.count()).select_from(Event)) == event_count

    before = dict(app.dependency_overrides)
    try:
        with TestClient(app) as client:
            denied = client.post('/orders/101/approve', params={'event_id': 'ok'})
            assert denied.status_code == 403
            assert denied.json() == {'detail': 'Access denied'}
            observe('PENDING', 0)
            app.dependency_overrides[actor] = lambda: 'alice'
            missing = client.post('/orders/999/approve', params={'event_id': 'ok'})
            assert missing.status_code == 404
            assert missing.json() == {'detail': 'Order not found'}
            failed = client.post('/orders/101/approve', params={'event_id': 'FAIL_DB'})
            assert failed.status_code == 409
            assert failed.json() == {'detail': 'Event rejected'}
            observe('PENDING', 0)
            success = client.post('/orders/101/approve', params={'event_id': 'ok'})
            assert success.status_code == 200
            assert success.json() == {'id': 101, 'status': 'APPROVED'}
            observe('APPROVED', 1)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(before)


def test_failed_flush_requires_rollback_before_reusing_session(database):
    with Session(database) as session:
        session.add(Event(order_id=101, event_id='FAIL_DB'))
        with pytest.raises(IntegrityError):
            session.flush()
        with pytest.raises(PendingRollbackError):
            session.get(Order, 101)
        session.rollback()
        assert session.get(Order, 101).status == 'PENDING'
