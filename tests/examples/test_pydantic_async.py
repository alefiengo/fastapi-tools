"""Executable v2 wire contracts and explicit HTTPX lifespan; no live server."""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, field_validator
import pytest


class Payload(BaseModel):
    note: str | None


class PublicPrice(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    amount: Decimal


def test_required_nullable_and_decimal_wire_contract():
    app = FastAPI()

    @app.post('/prices', response_model=PublicPrice)
    def price(payload: Payload):
        return {'amount': Decimal('12.50'), 'internal_cost': Decimal('2.00')}

    with TestClient(app) as client:
        missing = client.post('/prices', json={})
        assert missing.status_code == 422
        assert missing.json()['detail'][0]['loc'] == ['body', 'note']
        assert missing.json()['detail'][0]['type'] == 'missing'
        invalid = client.post('/prices', json={'note': []})
        assert invalid.status_code == 422
        assert invalid.json()['detail'][0]['type'] == 'string_type'
        nullable = client.post('/prices', json={'note': None})
        assert nullable.status_code == 200
        assert nullable.json() == {'amount': '12.50'}
        schemas = client.get('/openapi.json').json()['components']['schemas']
        assert schemas['Payload']['required'] == ['note']


def test_v2_validator_type_error_is_a_programming_error():
    class BrokenValidator(BaseModel):
        value: int

        @field_validator('value')
        @classmethod
        def validate_value(cls, value):
            raise TypeError('validator bug')

    with pytest.raises(TypeError, match='validator bug'):
        BrokenValidator(value=1)


def test_httpx_requires_explicit_lifespan_and_closes_after_failure():
    events = []

    @asynccontextmanager
    async def lifespan(app):
        events.append('startup')
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            events.append('shutdown')

    app = FastAPI(lifespan=lifespan)

    @app.get('/ready')
    async def ready():
        return {'ready': getattr(app.state, 'ready', False)}

    async def scenario():
        async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
            assert (await client.get('/ready')).json() == {'ready': False}
        assert events == []
        # This fixture app has one lifespan. Applications with mounted apps or
        # additional ASGI lifecycle needs should use their existing manager.
        with pytest.raises(RuntimeError, match='failure during request scope'):
            async with app.router.lifespan_context(app):
                async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
                    assert (await client.get('/ready')).json() == {'ready': True}
                    raise RuntimeError('failure during request scope')
        assert app.state.ready is False
        assert events == ['startup', 'shutdown']

    asyncio.run(scenario())
