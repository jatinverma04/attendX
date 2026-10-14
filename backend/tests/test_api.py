"""Backend regression tests (isolated scratch DB, never the seed database).

Requires MongoDB reachable via MONGO_URI (falls back to the local .env)
and test deps:  pip install -r requirements-test.txt
Run from backend/:  python -m pytest tests/ -q
"""
import concurrent.futures as cf
import os
from datetime import datetime, timedelta, timezone

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


def test_concurrent_patch_loses_no_history(seed, client):
    # Two racing PATCHes on one record: exactly one wins the compare-and-set,
    # the other must get 409 (never 500) and succeed on retry, so both
    # requested changes survive in history.
    tdb = seed
    t0 = datetime(2026, 7, 1, 3, 58, tzinfo=U)
    tdb.employees.insert_one(
        {"emp_code": "EMPT003", "name": "C", "email": "c@x.com",
         "department": "OPS", "shift_start": "09:30", "shift_end": "18:30",
         "joined_on": "2026-07-01", "created_at": t0})
    pi, po = 1783379880000, 1783412400000
    assert client.post("/attendance/punch-in",
                       json={"emp_code": "EMPT003",
                             "punched_at": pi}).status_code == 201
    r = client.post("/attendance/punch-out",
                    json={"emp_code": "EMPT003", "punched_at": po})
    assert r.status_code == 200
    date = r.json()["date"]
    url = f"/attendance/EMPT003/{date}"
    bodies = [
        {"status": "WFH", "reason": "race change A",
         "regularized_by": "pytest"},
        {"punch_out": po + 60000, "reason": "race change B",
         "regularized_by": "pytest"},
    ]
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        codes = list(ex.map(
            lambda b: TestClient(M.app, raise_server_exceptions=False)
                .patch(url, json=b).status_code,
            bodies))
    assert set(codes) <= {200, 409}, codes
    for body, code in zip(bodies, codes):
        if code == 409:
            assert client.patch(url, json=body).status_code == 200
    final = client.get("/attendance",
                       params={"emp_code": "EMPT003"}).json()["items"][0]
    fields = {k for e in final["history"] for k in e["changes"]}
    assert {"status", "punch_out"} <= fields, final["history"]


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


# --------------------------------------------------------------------------- #
# R1-R10 rule-exactness battery (scratch DB; rule text: PROBLEM_STATEMENT 6.)
# --------------------------------------------------------------------------- #
IST = timezone(timedelta(hours=5, minutes=30))


def _ms(y, mo, d, h, mi, s=0, ms=0):
    """Exact epoch-ms instant for an IST wall clock time."""
    whole = int(datetime(y, mo, d, h, mi, s, tzinfo=IST).timestamp() * 1000)
    return whole + ms


def _mk_emp(tdb, code, dept, joined, s0="09:30", s1="18:30"):
    tdb.employees.insert_one({
        "emp_code": code, "name": code, "email": f"{code.lower()}@x.com",
        "department": dept, "shift_start": s0, "shift_end": s1,
        "joined_on": joined, "created_at": datetime(2026, 7, 1, tzinfo=U),
    })


def _mk_log(tdb, code, date, status="PRESENT", late=0, ot=0, wh=None,
            hd=False):
    """Direct-seeded stored record, exactly as the grader writes them."""
    tdb.attendance_logs.insert_one({
        "emp_code": code, "date": date, "status": status,
        "punch_in": None, "punch_out": None, "work_hours": wh,
        "late_minutes": late, "overtime_minutes": ot, "half_day": hd,
        "history": [],
    })


def test_r1_truncation_and_r2_grace_boundaries(seed, client):
    tdb = seed
    _mk_emp(tdb, "EMPT011", "R1R2", "2026-07-01")
    # strictly-more-than-10:00 with sub-second input, truncated to whole seconds
    r = client.post("/attendance/punch-in", json={
        "emp_code": "EMPT011", "punched_at": _ms(2026, 7, 8, 9, 40, 1, 500)})
    assert r.status_code == 201
    b = r.json()
    assert b["punch_in"] == _ms(2026, 7, 8, 9, 40, 1)
    assert b["punch_in"] % 1000 == 0          # stored value is whole seconds
    assert b["date"] == "2026-07-08"
    assert b["late_minutes"] == 10            # 09:40:01 -> 10, not 0
    # exactly 10:00 after shift start -> grace, not late
    r = client.post("/attendance/punch-in", json={
        "emp_code": "EMPT011", "punched_at": _ms(2026, 7, 9, 9, 40, 0)})
    assert r.status_code == 201
    assert r.json()["late_minutes"] == 0
    # 10:15:59 -> whole minutes since shift start = 45
    r = client.post("/attendance/punch-in", json={
        "emp_code": "EMPT011", "punched_at": _ms(2026, 7, 10, 10, 15, 59)})
    assert r.status_code == 201
    assert r.json()["late_minutes"] == 45
    assert "_id" not in r.json()


def test_r1_overnight_date_with_r2_late(seed, client):
    tdb = seed
    _mk_emp(tdb, "EMPT012", "NIGHT", "2026-07-01", "22:00", "06:00")
    # 05:10 post-midnight punch belongs to the previous day's 22:00 shift
    r = client.post("/attendance/punch-in", json={
        "emp_code": "EMPT012", "punched_at": _ms(2026, 7, 9, 5, 10)})
    assert r.status_code == 201
    b = r.json()
    assert b["date"] == "2026-07-08"           # shift started the previous day
    assert b["late_minutes"] == 430            # since 07-08 22:00, not 0
    # punch-out across midnight: R4/R3/R5 on the overnight record
    r = client.post("/attendance/punch-out", json={
        "emp_code": "EMPT012", "punched_at": _ms(2026, 7, 9, 6, 30)})
    assert r.status_code == 200
    b = r.json()
    assert b["work_hours"] == 1.33             # 1h20m, 2dp half-up
    assert b["overtime_minutes"] == 30          # >=30 past the 06:00 end
    assert b["half_day"] is True                # 1.33 < 4.50
    # exactly at shift_end is not "earlier than shift_end" -> current day
    r = client.post("/attendance/punch-in", json={
        "emp_code": "EMPT012", "punched_at": _ms(2026, 7, 10, 6, 0)})
    assert r.status_code == 201
    b = r.json()
    assert b["date"] == "2026-07-10" and b["late_minutes"] == 0


def test_r3_overtime_gate(seed, client):
    tdb = seed
    _mk_emp(tdb, "EMPT013", "R3", "2026-07-01")
    # 29:59 past shift end -> gate is >= 30 -> 0
    client.post("/attendance/punch-in", json={
        "emp_code": "EMPT013", "punched_at": _ms(2026, 7, 13, 9, 30)})
    r = client.post("/attendance/punch-out", json={
        "emp_code": "EMPT013", "punched_at": _ms(2026, 7, 13, 18, 59, 59)})
    assert r.status_code == 200
    b = r.json()
    assert b["overtime_minutes"] == 0
    assert b["work_hours"] == 9.50              # 34199s -> 9.4997 -> 9.50
    # exactly 30 minutes past shift end -> 30
    client.post("/attendance/punch-in", json={
        "emp_code": "EMPT013", "punched_at": _ms(2026, 7, 14, 9, 30)})
    r = client.post("/attendance/punch-out", json={
        "emp_code": "EMPT013", "punched_at": _ms(2026, 7, 14, 19, 0)})
    assert r.status_code == 200
    b = r.json()
    assert b["overtime_minutes"] == 30 and b["work_hours"] == 9.5
    assert b["half_day"] is False


def test_r4_half_up_and_r5_half_day_boundary(seed, client):
    tdb = seed
    _mk_emp(tdb, "EMPT014", "R5", "2026-07-01")
    cases = [
        ((2026, 7, 13, 10, 30, 18), 1.01, True),   # 3618s = 1.005h -> 1.01
        ((2026, 7, 14, 14, 0, 0), 4.5, False),     # exactly 4.50 -> not half
        ((2026, 7, 15, 13, 59, 41), 4.49, True),   # rounds below 4.50
        ((2026, 7, 16, 13, 59, 42), 4.5, False),   # 4.495 half-up to 4.50
    ]
    for out, wh, hd in cases:
        client.post("/attendance/punch-in", json={
            "emp_code": "EMPT014", "punched_at": _ms(2026, 7, out[2], 9, 30)})
        r = client.post("/attendance/punch-out", json={
            "emp_code": "EMPT014", "punched_at": _ms(*out)})
        assert r.status_code == 200, out
        assert r.json()["work_hours"] == wh, out
        assert r.json()["half_day"] is hd, out


@pytest.fixture(scope="module")
def qaux(seed):
    """Stored analytics dataset: weekday/weekend, leave, mid-month and
    next-month joiners (R7/R9), plus late totals for ranking ties."""
    tdb = seed
    _mk_emp(tdb, "EMPT020", "QAUX", "2026-07-01")
    _mk_emp(tdb, "EMPT021", "QAUX", "2026-07-20")
    _mk_emp(tdb, "EMPT022", "QAUX", "2026-08-01")
    _mk_emp(tdb, "EMPT024", "QAUX", "2026-07-01")
    _mk_emp(tdb, "EMPT025", "QAUX", "2026-07-01")
    _mk_log(tdb, "EMPT020", "2026-07-06", late=30, ot=45, wh=8.0)  # Mon
    _mk_log(tdb, "EMPT020", "2026-07-07", status="LEAVE")
    _mk_log(tdb, "EMPT020", "2026-07-08", status="WFH", wh=7.5)
    _mk_log(tdb, "EMPT020", "2026-07-11", late=45, wh=8.0)  # Sat: late counts
    _mk_log(tdb, "EMPT024", "2026-07-02", late=10, wh=8.0)
    _mk_log(tdb, "EMPT024", "2026-07-08", wh=8.0)
    _mk_log(tdb, "EMPT021", "2026-07-22", late=75, wh=8.0)
    return tdb


def test_r6_r7_monthly_presence_weekend_and_rounding(qaux, client):
    r = client.get("/analytics/employees/EMPT020/monthly",
                   params={"month": "2026-07"})
    assert r.status_code == 200
    b = r.json()
    assert b["working_days"] == 23          # R7: Mon-Fri, July 2026
    assert b["present_days"] == 2.0          # weekend row excluded
    assert b["leave_days"] == 1
    assert b["late_count"] == 2              # weekend row still adds late
    assert b["total_late_minutes"] == 75
    assert b["total_overtime_minutes"] == 45
    assert b["attendance_pct"] == 8.70       # R8: 2dp half-up
    assert "_id" not in b


def test_r9_r8_department_summary(qaux, client):
    r = client.get("/analytics/departments/summary",
                   params={"month": "2026-07", "department": "QAUX"})
    assert r.status_code == 200
    row = next(x for x in r.json()["items"]
               if x["department"] == "QAUX")
    assert row["headcount"] == 4             # R9: Aug joiner excluded
    assert row["present_days"] == 5.0         # weekend present not counted
    assert row["avg_work_hours"] == 7.92     # 47.5/6 -> 7.9166 -> 7.92
    assert row["late_count"] == 4
    assert row["total_late_minutes"] == 160
    assert row["leave_count"] == 1
    assert row["on_duty_count"] == 0
    assert "_id" not in row


def test_r8_trend_gaps_and_4dp_rate(qaux, client):
    r = client.get("/analytics/departments/QAUX/trend",
                   params={"from": "2026-07-06", "to": "2026-07-12"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [x["date"] for x in items] == [
        "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09",
        "2026-07-10", "2026-07-11", "2026-07-12"]      # gap-filled, no holes
    by = {x["date"]: x for x in items}
    assert by["2026-07-06"]["is_working_day"] is True
    assert by["2026-07-06"]["headcount"] == 3
    assert by["2026-07-06"]["attendance_rate"] == 0.3333   # R8 4dp half-up
    assert by["2026-07-07"]["attendance_rate"] == 0.0
    assert by["2026-07-08"]["attendance_rate"] == 0.6667   # 2/3 -> 0.6667
    ma = by["2026-07-07"]["moving_avg_7d"]
    assert isinstance(ma, (int, float)) and 0.1666 <= ma <= 0.1667
    assert by["2026-07-11"]["is_working_day"] is False
    assert by["2026-07-11"]["attendance_rate"] is None      # weekend: no rate
    assert by["2026-07-11"]["present_count"] == 1.0         # row still kept
    assert client.get("/analytics/departments/QAUX/trend",
                      params={"from": "2026-01-01",
                              "to": "2026-07-01"}).status_code == 422


def test_leaderboard_ties_rank_sequence(qaux, client):
    r = client.get("/analytics/leaderboard/late",
                   params={"month": "2026-07", "department": "QAUX"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [(x["emp_code"], x["rank"], x["total_late_minutes"])
            for x in items] == [
        ("EMPT020", 1, 75), ("EMPT021", 1, 75), ("EMPT024", 3, 10)]
    assert all("_id" not in x for x in items)


def test_r10_pagination_bounds_and_409(qaux, client):
    assert client.get("/employees", params={"page": 0}).status_code == 422
    assert client.get("/employees",
                      params={"page_size": 101}).status_code == 422
    r = client.get("/employees", params={"department": "QAUX",
                                         "page": 2, "page_size": 1})
    b = r.json()
    # total reflects the filter (all 5 QAUX employees, Aug joiner included)
    assert (b["total"], b["page"], len(b["items"])) == (5, 2, 1)
    # Create -> 201, duplicate emp_code -> 409 (unique DB index)
    new_emp = {"emp_code": "EMP90001", "name": "Dup", "email": "dup@x.com",
               "department": "QAUX", "joined_on": "2026-07-01"}
    assert client.post("/employees", json=new_emp).status_code == 201
    assert client.post("/employees", json=new_emp).status_code == 409
    it = client.get("/employees",
                    params={"department": "R1R2"}).json()["items"][0]
    assert isinstance(it["created_at"], int) and it["created_at"] > 10 ** 12
    assert "_id" not in it


def test_concurrent_duplicate_create_single_winner(seed, client):
    # Contract: concurrent duplicate creates yield exactly one 201, rest 409.
    body = {"emp_code": "EMP90002", "name": "Race", "email": "race@x.com",
            "department": "RACE", "joined_on": "2026-07-01"}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(
            lambda _: TestClient(M.app, raise_server_exceptions=False)
                .post("/employees", json=body).status_code,
            range(6)))
    assert codes.count(201) == 1 and codes.count(409) == 5, codes
    assert 500 not in codes


def test_analytics_execute_as_mongo_aggregations(qaux, client):
    """Analytics must run as $group pipelines inside MongoDB, never by
    loading attendance documents into Python loops."""
    import pymongo.collection as _pc
    agg_calls, find_calls = [], []
    orig_agg, orig_find = _pc.Collection.aggregate, _pc.Collection.find

    def spy_agg(coll, pipeline, *a, **k):
        agg_calls.append((coll.name, pipeline))
        return orig_agg(coll, pipeline, *a, **k)

    def spy_find(coll, *a, **k):
        find_calls.append(coll.name)
        return orig_find(coll, *a, **k)

    _pc.Collection.aggregate, _pc.Collection.find = spy_agg, spy_find
    try:
        calls = [
            ("/analytics/employees/EMPT020/monthly", {"month": "2026-07"}),
            ("/analytics/departments/summary", {"month": "2026-07"}),
            ("/analytics/leaderboard/late", {"month": "2026-07"}),
            ("/analytics/departments/QAUX/trend",
             {"from": "2026-07-06", "to": "2026-07-12"}),
        ]
        for path, params in calls:
            assert client.get(path, params=params).status_code == 200, path
    finally:
        _pc.Collection.aggregate, _pc.Collection.find = orig_agg, orig_find

    # No attendance scan-fetch; every analytics read is a pipeline stage set.
    assert "attendance_logs" not in find_calls, find_calls
    names = {n for n, _ in agg_calls}
    assert "attendance_logs" in names and "employees" in names, names
    for name, pipe in agg_calls:
        assert any("$group" in stage for stage in pipe), (name, pipe)
