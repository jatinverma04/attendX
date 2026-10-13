"""Backend regression tests (isolated scratch DB, never the seed database).

Requires MongoDB reachable via MONGO_URI (falls back to the local .env)
and test deps:  pip install -r requirements-test.txt
Run from backend/:  python -m pytest tests/ -q
"""
import concurrent.futures as cf
import os
from datetime import datetime, timezone

import pytest

U = timezone.utc

try:
    from fastapi.testclient import TestClient
    import app.main as M
except Exception as exc:  # pragma: no cover - missing test deps
    pytest.skip(f"test deps unavailable: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def tdb():
    try:
        M.client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB unreachable")
    name = os.getenv("TEST_MONGO_DB", "attendx_pytest")
    db = M.client[name]
    db.employees.delete_many({})
    db.attendance_logs.delete_many({})
    M.db = db
    M._ensure_indexes()
    yield db
    db.employees.delete_many({})
    db.attendance_logs.delete_many({})


@pytest.fixture(scope="module")
def seed(tdb):
    t0 = datetime(2026, 7, 1, 3, 58, tzinfo=U)
    tdb.employees.insert_many([
        {"emp_code": "EMPT001", "name": "A", "email": "a@x.com",
         "department": "ENG", "shift_start": "09:30", "shift_end": "18:30",
         "joined_on": "2026-07-01", "created_at": t0},
        {"emp_code": "EMPT002", "name": "B", "email": "b@x.com",
         "department": "QA", "shift_start": "09:30", "shift_end": "18:30",
         "joined_on": "2026-07-15", "created_at": t0},
    ])
    return tdb


@pytest.fixture(scope="module")
def client():
    return TestClient(M.app, raise_server_exceptions=False)


def test_department_filter_and_total(seed, client):
    r = client.get("/employees", params={"department": "ENG"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [x["emp_code"] for x in body["items"]] == ["EMPT001"]
    assert "_id" not in body["items"][0]


def test_clear_filter_restores_all(seed, client):
    r = client.get("/employees", params={"page_size": 100})
    assert r.json()["total"] == 2


def test_unknown_department_empty(seed, client):
    r = client.get("/employees", params={"department": "Nope"})
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_employee_validation(seed, client):
    bad = {"emp_code": "BAD", "name": "n", "email": "a@b.c",
           "department": "d", "joined_on": "2026-07-01"}
    assert client.post("/employees", json=bad).status_code == 422
    same_shift = dict(bad, emp_code="EMPT010", email="v@x.com",
                      shift_start="09:30", shift_end="09:30")
    assert client.post("/employees", json=same_shift).status_code == 422


def test_punch_in_out_validation(seed, client):
    assert client.post("/attendance/punch-in",
                       json={"emp_code": "NOPE"}).status_code == 404
    body = {"emp_code": "EMPT001", "punched_at": 123}
    assert client.post("/attendance/punch-in", json=body).status_code == 422
    body = {"emp_code": "EMPT001", "status": "ABSENT"}
    assert client.post("/attendance/punch-in", json=body).status_code == 422


def test_parallel_punch_in_single_winner(seed, client):
    pi = 1783379880000
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(
            lambda _: TestClient(M.app, raise_server_exceptions=False).post(
                "/attendance/punch-in",
                json={"emp_code": "EMPT002", "punched_at": pi}).status_code,
            range(8)))
    assert codes.count(201) == 1 and codes.count(409) == 7
    assert 500 not in codes


def test_parallel_punch_out_single_winner(seed, client):
    po = 1783412400000
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(
            lambda _: TestClient(M.app, raise_server_exceptions=False).post(
                "/attendance/punch-out",
                json={"emp_code": "EMPT002", "punched_at": po}).status_code,
            range(8)))
    assert codes.count(200) == 1 and codes.count(409) == 7


def test_patch_recomputes_and_appends_history(seed, client):
    date = client.get("/attendance",
                      params={"emp_code": "EMPT002"}).json()["items"][0]["date"]
    r = client.patch(f"/attendance/EMPT002/{date}",
                     json={"status": "WFH", "reason": "regression reason",
                           "regularized_by": "pytest"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "WFH"
    assert len(body["history"]) == 1
    assert body["history"][0]["changes"]["status"] == {
        "from": "PRESENT", "to": "WFH"}
    # identical repeat changes nothing
    r = client.patch(f"/attendance/EMPT002/{date}",
                     json={"status": "WFH", "reason": "regression reason",
                           "regularized_by": "pytest"})
    assert r.status_code == 422


def test_monthly_math(seed, client):
    r = client.get("/analytics/employees/EMPT002/monthly",
                   params={"month": "2026-07"})
    assert r.status_code == 200
    body = r.json()
    assert body["working_days"] == 13  # joined 07-15
    assert body["present_days"] == 1.0


def test_explain_uses_indexes(seed, client):
    import json as _json
    cases = [
        ("attendance_list", {}),
        ("employee_monthly", {"emp_code": "EMPT002", "month": "2026-07"}),
        ("department_summary", {"month": "2026-07"}),
        ("late_leaderboard", {"month": "2026-07"}),
        ("department_trend", {"department": "ENG", "from": "2026-07-01",
                              "to": "2026-07-05"}),
    ]
    for ep, params in cases:
        r = client.get(f"/admin/explain/{ep}", params=params)
        assert r.status_code == 200, ep
        s = _json.dumps(r.json()["explain"])
        assert "IXSCAN" in s and "COLLSCAN" not in s, ep
