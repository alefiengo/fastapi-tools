"""Real FastAPI routing, schema, lifespan, override and rollback smoke tests."""
from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
import pytest


def actor():
    return "anonymous"


@asynccontextmanager
async def lifespan(app):
    app.state.ready = True
    yield
    app.state.ready = False


app = FastAPI(lifespan=lifespan)
router = APIRouter(prefix="/products")


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductRead(ProductCreate):
    id: int


@router.post("", response_model=ProductRead, status_code=201)
def create(payload: ProductCreate, current_actor: str = Depends(actor)):
    if current_actor != "alice":
        raise HTTPException(status_code=403, detail="Access denied")
    return {"id": 1, "name": payload.name, "internal_secret": "hidden"}


@app.get("/health")
def health():
    return {"status": "ok" if app.state.ready else "down"}


app.include_router(router, prefix="/api/v1")


def test_lifespan_health_and_schema():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        schema = client.get("/openapi.json").json()
        assert "/api/v1/products" in schema["paths"]
        assert schema["paths"]["/api/v1/products"]["post"]["responses"]["201"]
    assert app.state.ready is False


def test_auth_validation_and_filtered_response():
    before = dict(app.dependency_overrides)
    try:
        with TestClient(app) as client:
            denied = client.post("/api/v1/products", json={"name": "chair"})
            assert denied.status_code == 403
            assert denied.json() == {"detail": "Access denied"}
            app.dependency_overrides[actor] = lambda: "alice"
            response = client.post("/api/v1/products", json={"name": "chair"})
            assert response.status_code == 201
            assert response.json() == {"id": 1, "name": "chair"}
            invalid = client.post("/api/v1/products", json={"name": ""})
            assert invalid.status_code == 422
            assert invalid.json()["detail"][0]["loc"] == ["body", "name"]
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(before)


def load_fixture(name):
    path = Path(__file__).resolve().parents[2] / "evals/test-writer-behavior/fixtures" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_ownership_success_and_real_rollback(tmp_path):
    data, service = load_fixture("fixture_data"), load_fixture("order_service")
    database = tmp_path / "orders.db"
    data.seed(database)
    orders = service.OrderService(database)
    with pytest.raises(service.OrderAccessDenied):
        orders.approve(101, "bob", "event")
    assert data.status(database) == "PENDING"
    with pytest.raises(LookupError):
        orders.approve(999, "alice", "event")
    with pytest.raises(sqlite3.IntegrityError):
        orders.approve(101, "alice", "FAIL_DB")
    assert data.status(database) == "PENDING"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    orders.approve(101, "alice", "ok")
    assert data.status(database) == "APPROVED"


def test_shared_runtime_verifies_real_fastapi_project(tmp_path):
    import json
    import subprocess
    import sys

    runtime = Path(__file__).resolve().parents[2] / "runtime/project_runtime.py"
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\nhttpx\n")
    (tmp_path / "main.py").write_text('from fastapi import FastAPI\napp=FastAPI()\n@app.get("/hello")\ndef hello(): return {"message":"hello"}\n')
    (tmp_path / "test_app.py").write_text('from fastapi.testclient import TestClient\nfrom main import app\ndef test_hello():\n    with TestClient(app) as client:\n        assert client.get("/hello").json() == {"message":"hello"}\n')

    def invoke(**options):
        request = {"action": "run", "projectRoot": str(tmp_path), "task": "verify", **options}
        result = subprocess.run([sys.executable, str(runtime)], input=json.dumps(request), text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    verified = invoke()
    assert verified["ok"], verified
    assert verified["reused"] is False
    assert invoke()["reused"] is True
    tested = invoke(task="test", collectTestReports=True)
    assert tested["ok"], tested
    assert len(tested["testReports"]) == 1
    assert 'tests="1"' in tested["testReports"][0]["content"]
