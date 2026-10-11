"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)
"""
import os
import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")

EPOCH_MIN = 100000000000
EPOCH_MAX = 4102444800000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

EpochMillis = Annotated[int, Field(strict=True, ge=EPOCH_MIN, le=EPOCH_MAX)]


def _ensure_indexes():
    try:
        db.employees.create_index([("emp_code", ASCENDING)], unique=True, name="uniq_emp_code")
        db.attendance_logs.create_index(
            [("emp_code", ASCENDING), ("date", ASCENDING)], unique=True, name="uniq_emp_date"
        )
        db.attendance_logs.create_index(
            [("date", DESCENDING), ("emp_code", ASCENDING)], name="idx_date_emp"
        )
        db.employees.create_index([("department", ASCENDING), ("emp_code", ASCENDING)],
                                  name="idx_dept_emp")
    except Exception:
        pass  # Mongo down at import; retried on startup so /health can still report 503


_ensure_indexes()


@app.on_event("startup")
def _startup_indexes():
    _ensure_indexes()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _truncate_seconds(dt: datetime) -> datetime:
    return dt.replace(microsecond=0)


def ms_to_dt(ms: int) -> datetime:
    return _truncate_seconds(datetime.fromtimestamp(ms / 1000, tz=UTC))


def dt_to_ms(dt: datetime) -> int:
    return int(_as_utc(_truncate_seconds(dt)).timestamp() * 1000)


def _parse_hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def attendance_date_for(punch_utc: datetime, shift_start: str, shift_end: str) -> str:
    punch_ist = _as_utc(punch_utc).astimezone(IST)
    d = punch_ist.date()
    sh, sm = _parse_hm(shift_start)
    eh, em = _parse_hm(shift_end)
    overnight = (eh, em) <= (sh, sm)
    if overnight and (punch_ist.hour, punch_ist.minute, punch_ist.second) < (eh, em, 0):
        # Punch belongs to shift that started the previous day; count exact
        # shift-end instant as the new day (strictly earlier -> previous day).
        d = d - timedelta(days=1)
    return d.isoformat()


def _shift_start_ist(date_str: str, shift_start: str) -> datetime:
    h, m = _parse_hm(shift_start)
    d = date_cls.fromisoformat(date_str)
    return datetime(d.year, d.month, d.day, h, m, 0, tzinfo=IST)


def _shift_end_ist(date_str: str, shift_start: str, shift_end: str) -> datetime:
    h, m = _parse_hm(shift_end)
    d = date_cls.fromisoformat(date_str)
    dt = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=IST)
    sh, sm = _parse_hm(shift_start)
    if (h, m) <= (sh, sm):
        dt = dt + timedelta(days=1)
    return dt


def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    punch_utc = _truncate_seconds(_as_utc(punch_in))
    punch_ist = punch_utc.astimezone(IST)
    h, m = _parse_hm(shift_start)
    start = punch_ist.replace(hour=h, minute=m, second=0, microsecond=0)
    diff = (punch_ist - start).total_seconds()
    if diff <= 600:
        return 0
    return int(diff // 60)


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    secs = Decimal(str((_as_utc(punch_out) - _as_utc(punch_in)).total_seconds()))
    return float((secs / Decimal("3600")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_overtime(punch_out: datetime, shift_end: str, date_str: str,
                     shift_start: Optional[str] = None) -> int:
    punch_utc = _as_utc(punch_out)
    if shift_start is not None:
        end = _shift_end_ist(date_str, shift_start, shift_end)
    else:
        h, m = _parse_hm(shift_end)
        d = date_cls.fromisoformat(date_str)
        end = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=IST)
        if punch_utc < end.astimezone(UTC) - timedelta(hours=20):
            end = end + timedelta(days=1)
    diff_min = int((punch_utc - end.astimezone(UTC)).total_seconds() // 60)
    return diff_min if diff_min >= 30 else 0


def _history_to_api(history) -> list:
    out = []
    for e in history or []:
        changes = {}
        for k, v in (e.get("changes") or {}).items():
            f, t = v.get("from"), v.get("to")
            if k in ("punch_in", "punch_out"):
                f = dt_to_ms(f) if isinstance(f, datetime) else f
                t = dt_to_ms(t) if isinstance(t, datetime) else t
            changes[k] = {"from": f, "to": t}
        at = e.get("at")
        out.append({
            "at": dt_to_ms(at) if isinstance(at, datetime) else at,
            "by": e.get("by"),
            "reason": e.get("reason"),
            "changes": changes,
        })
    return out


def serialize_employee(doc: dict) -> dict:
    created = doc.get("created_at")
    return {
        "emp_code": doc.get("emp_code"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "department": doc.get("department"),
        "shift_start": doc.get("shift_start", "09:30"),
        "shift_end": doc.get("shift_end", "18:30"),
        "joined_on": doc.get("joined_on"),
        "created_at": dt_to_ms(created) if isinstance(created, datetime) else created,
    }


def serialize_attendance(doc: dict) -> dict:
    pi = doc.get("punch_in")
    po = doc.get("punch_out")
    return {
        "emp_code": doc.get("emp_code"),
        "date": doc.get("date"),
        "status": doc.get("status"),
        "punch_in": dt_to_ms(pi) if isinstance(pi, datetime) else None,
        "punch_out": dt_to_ms(po) if isinstance(po, datetime) else None,
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0) if doc.get("late_minutes") is not None else 0,
        "overtime_minutes": doc.get("overtime_minutes", 0) if doc.get("overtime_minutes") is not None else 0,
        "half_day": bool(doc.get("half_day", False)),
        "history": _history_to_api(doc.get("history") or []),
    }


def _validate_date_str(value: str, field: str) -> str:
    if not DATE_RE.match(value or ""):
        raise HTTPException(422, f"invalid {field}")
    try:
        date_cls.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"invalid {field}")
    return value


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(default="09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field(default="18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str

    @model_validator(mode="after")
    def _check_dates_shifts(self):
        try:
            date_cls.fromisoformat(self.joined_on)
        except ValueError:
            raise ValueError("invalid joined_on")
        if not DATE_RE.match(self.joined_on):
            raise ValueError("invalid joined_on")
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[EpochMillis] = None
    status: str = "PRESENT"

    @model_validator(mode="after")
    def _check_status(self):
        if self.status not in ("PRESENT", "WFH", "ON_DUTY"):
            raise ValueError("invalid status")
        return self


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except Exception:
        raise HTTPException(503, "mongodb unavailable")
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(UTC).replace(microsecond=0)
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return serialize_employee(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q: dict = {}
    if department:
        q["department"] = department
    total = db.employees.count_documents(q)
    cursor = (
        db.employees.find(q, {"_id": 0})
        .sort("emp_code", ASCENDING)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [serialize_employee(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(404, "unknown employee")
    ts = ms_to_dt(body.punched_at) if body.punched_at is not None else \
        datetime.now(UTC).replace(microsecond=0)
    d = attendance_date_for(ts, emp.get("shift_start", "09:30"), emp.get("shift_end", "18:30"))
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": _as_utc(ts),
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp.get("shift_start", "09:30")),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    doc.pop("_id", None)
    return serialize_attendance(doc)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if date_from:
        _validate_date_str(date_from, "date_from")
    if date_to:
        _validate_date_str(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from > date_to")
    if status is not None and status not in ("PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"):
        raise HTTPException(422, "invalid status")
    q: dict = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    total = db.attendance_logs.count_documents(q)
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [serialize_attendance(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
