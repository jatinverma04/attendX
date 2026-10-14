"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)
"""
import calendar as _calendar
import json as _json
import os
import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional

from bson import json_util
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")

# Browser dashboards (Vite dev server, previews) call this API cross-origin.
# The API uses no cookies or auth headers, so a wildcard origin is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

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
        db.employees.create_index([("joined_on", ASCENDING)], name="idx_joined_on")
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


def compute_late_minutes(punch_in: datetime, shift_start: str,
                         date_str: str) -> int:
    punch_utc = _truncate_seconds(_as_utc(punch_in))
    punch_ist = punch_utc.astimezone(IST)
    # Anchor at the record's shift-start instant, not the punch's own calendar
    # day: an overnight shift's post-midnight punch belongs to the previous
    # day's 22:00 start (R2 counts minutes since that shift_start).
    start = _shift_start_ist(date_str, shift_start)
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


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[EpochMillis] = None


class RegularizeIn(BaseModel):
    status: Optional[str] = None
    punch_in: Optional[EpochMillis] = None
    punch_out: Optional[EpochMillis] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _check_status(self):
        if self.status is not None and self.status not in (
            "PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"
        ):
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
        "late_minutes": compute_late_minutes(
            ts, emp.get("shift_start", "09:30"), d),
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


@app.post("/attendance/punch-out", status_code=200)
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(404, "unknown employee")
    ts = ms_to_dt(body.punched_at) if body.punched_at is not None else \
        datetime.now(UTC).replace(microsecond=0)
    ts_utc = _as_utc(ts)
    rec = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": ts_utc, "$ne": None}},
        sort=[("punch_in", DESCENDING)],
    )
    if rec is None:
        raise HTTPException(404, "no punch-in found")
    pi = _as_utc(rec["punch_in"]) if isinstance(rec.get("punch_in"), datetime) else None
    if pi is None:
        raise HTTPException(404, "no punch-in found")
    if ts_utc <= pi:
        raise HTTPException(422, "punched_at must be after punch_in")
    if (ts_utc - pi).total_seconds() > 24 * 3600:
        raise HTTPException(422, "punched_at more than 24 hours after punch_in")
    if rec.get("punch_out") is not None:
        raise HTTPException(409, "already punched out")
    shift_start = emp.get("shift_start", "09:30")
    shift_end = emp.get("shift_end", "18:30")
    work_hours = compute_work_hours(pi, ts_utc)
    overtime = compute_overtime(ts_utc, shift_end, rec["date"], shift_start)
    half_day = work_hours < 4.50
    updated = db.attendance_logs.find_one_and_update(
        {"_id": rec["_id"], "punch_out": None},
        {"$set": {
            "punch_out": ts_utc,
            "work_hours": work_hours,
            "overtime_minutes": overtime,
            "half_day": half_day,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        cur = db.attendance_logs.find_one({"_id": rec["_id"]})
        if cur is not None and cur.get("punch_out") is not None:
            raise HTTPException(409, "already punched out")
        raise HTTPException(404, "no punch-in found")
    return serialize_attendance(updated)


@app.patch("/attendance/{emp_code}/{date}", status_code=200)
def regularize_attendance(emp_code: str, date: str, body: RegularizeIn):
    _validate_date_str(date, "date")
    emp = db.employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(404, "unknown employee")
    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if rec is None:
        raise HTTPException(404, "no record for that date")
    shift_start = emp.get("shift_start", "09:30")
    shift_end = emp.get("shift_end", "18:30")

    old_status = rec.get("status")
    old_pi = rec.get("punch_in")
    old_po = rec.get("punch_out")
    old_pi = old_pi if isinstance(old_pi, datetime) else None
    old_po = old_po if isinstance(old_po, datetime) else None
    old_wh = rec.get("work_hours")
    old_late = rec.get("late_minutes", 0) if rec.get("late_minutes") is not None else 0
    old_ot = rec.get("overtime_minutes", 0) if rec.get("overtime_minutes") is not None else 0
    old_hd = bool(rec.get("half_day", False))
    hist = rec.get("history") or []

    new_status = body.status if body.status is not None else old_status
    pi_supplied = body.punch_in is not None
    po_supplied = body.punch_out is not None

    if new_status in ("ABSENT", "LEAVE"):
        if pi_supplied or po_supplied:
            raise HTTPException(422, "punch times not allowed with ABSENT/LEAVE")
        new_pi, new_po = None, None
    else:
        new_pi = ms_to_dt(body.punch_in) if pi_supplied else old_pi
        new_po = ms_to_dt(body.punch_out) if po_supplied else old_po
        if new_pi is None:
            raise HTTPException(422, "presence status requires punch_in")
        if attendance_date_for(_as_utc(new_pi), shift_start, shift_end) != date:
            raise HTTPException(422, "punch_in must stay on the record's date")
        if new_po is not None:
            new_pi_utc, new_po_utc = _as_utc(new_pi), _as_utc(new_po)
            if new_po_utc <= new_pi_utc:
                raise HTTPException(422, "punch_out must be after punch_in")
            if (new_po_utc - new_pi_utc).total_seconds() > 24 * 3600:
                raise HTTPException(422, "punch_out more than 24 hours after punch_in")

    if new_status in ("ABSENT", "LEAVE"):
        new_late, new_wh, new_ot, new_hd = 0, None, 0, False
    elif new_pi is None:
        new_late, new_wh, new_ot, new_hd = 0, None, 0, False
    else:
        new_late = compute_late_minutes(_as_utc(new_pi), shift_start, date)
        if new_po is None:
            new_wh, new_ot, new_hd = None, 0, False
        else:
            new_wh = compute_work_hours(_as_utc(new_pi), _as_utc(new_po))
            new_ot = compute_overtime(_as_utc(new_po), shift_end, date, shift_start)
            new_hd = new_wh < 4.50

    def _ms(v):
        return dt_to_ms(v) if isinstance(v, datetime) else None

    changes: dict = {}
    if new_status != old_status:
        changes["status"] = {"from": old_status, "to": new_status}
    if _ms(new_pi) != _ms(old_pi):
        changes["punch_in"] = {"from": _ms(old_pi), "to": _ms(new_pi)}
    if _ms(new_po) != _ms(old_po):
        changes["punch_out"] = {"from": _ms(old_po), "to": _ms(new_po)}
    if new_wh != old_wh:
        changes["work_hours"] = {"from": old_wh, "to": new_wh}
    if new_late != old_late:
        changes["late_minutes"] = {"from": old_late, "to": new_late}
    if new_ot != old_ot:
        changes["overtime_minutes"] = {"from": old_ot, "to": new_ot}
    if new_hd != old_hd:
        changes["half_day"] = {"from": old_hd, "to": new_hd}
    if not changes:
        raise HTTPException(422, "request changes nothing")

    now = datetime.now(UTC).replace(microsecond=0)
    entry_changes: dict = {}
    for k, v in changes.items():
        if k in ("punch_in", "punch_out"):
            entry_changes[k] = {
                "from": ms_to_dt(v["from"]) if v["from"] is not None else None,
                "to": ms_to_dt(v["to"]) if v["to"] is not None else None,
            }
        else:
            entry_changes[k] = v
    entry = {"at": now, "by": body.regularized_by, "reason": body.reason,
             "changes": entry_changes}

    filt: dict = {"_id": rec["_id"], f"history.{len(hist)}": {"$exists": False}}
    filt["status"] = {"$eq": old_status}
    filt["punch_in"] = {"$eq": old_pi} if old_pi is not None else None
    filt["punch_out"] = {"$eq": old_po} if old_po is not None else None
    updated = db.attendance_logs.find_one_and_update(
        filt,
        {"$set": {
            "status": new_status,
            "punch_in": _as_utc(new_pi) if new_pi is not None else None,
            "punch_out": _as_utc(new_po) if new_po is not None else None,
            "work_hours": new_wh,
            "late_minutes": new_late,
            "overtime_minutes": new_ot,
            "half_day": new_hd,
        }, "$push": {"history": entry}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(409, "concurrent modification, retry")
    return serialize_attendance(updated)


# --------------------------------------------------------------------------- #
# Analytics (Phase C) - aggregation pipelines, stored values are authoritative
# --------------------------------------------------------------------------- #
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PRESENCE = ["PRESENT", "WFH", "ON_DUTY"]


def _validate_month(month: Optional[str], field: str = "month") -> str:
    if not month or not MONTH_RE.match(month):
        raise HTTPException(422, f"invalid {field}")
    return month


def _month_bounds(month: str) -> tuple[str, str, str]:
    y, m = int(month[:4]), int(month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last = _calendar.monthrange(y, m)[1]
    return f"{month}-01", f"{ny:04d}-{nm:02d}-01", f"{month}-{last:02d}"


def _working_days(month: str, joined_on: str) -> int:
    y, m = int(month[:4]), int(month[5:7])
    last = _calendar.monthrange(y, m)[1]
    start = 1
    if joined_on[:7] == month:
        start = int(joined_on[8:10])
    elif joined_on[:7] > month:
        return 0
    return sum(1 for d in range(start, last + 1)
               if date_cls(y, m, d).weekday() < 5)


def _round2(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _dow_expr(date_field: str = "$date") -> dict:
    return {"$dayOfWeek": {"$dateFromString": {"dateString": date_field}}}


def _is_wd_expr(date_field: str = "$date") -> dict:
    dow = _dow_expr(date_field)
    return {"$and": [{"$gte": [dow, 2]}, {"$lte": [dow, 6]}]}


def _present_w_expr() -> dict:
    return {"$cond": [
        {"$and": [{"$in": ["$status", PRESENCE]}, _is_wd_expr()]},
        {"$cond": [{"$eq": [{"$ifNull": ["$half_day", False]}, True]}, 0.5, 1.0]},
        0.0,
    ]}


def _late_flag_expr() -> dict:
    return {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}


def _monthly_pipeline(emp_code: str, m_start: str, m_next: str) -> list:
    return [
        {"$match": {"emp_code": emp_code,
                    "date": {"$gte": m_start, "$lt": m_next}}},
        {"$group": {
            "_id": None,
            "present_days": {"$sum": _present_w_expr()},
            "leave_days": {"$sum": {"$cond": [
                {"$eq": ["$status", "LEAVE"]}, 1, 0]}},
            "late_count": {"$sum": _late_flag_expr()},
            "total_late_minutes": {"$sum": {
                "$ifNull": ["$late_minutes", 0]}},
            "total_overtime_minutes": {"$sum": {
                "$ifNull": ["$overtime_minutes", 0]}},
        }},
    ]


def _dept_summary_pipeline(emp_match: dict, m_start: str, m_next: str) -> list:
    return [
        {"$match": emp_match},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"ec": "$emp_code"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$emp_code", "$$ec"]},
                    {"$gte": ["$date", m_start]},
                    {"$lt": ["$date", m_next]},
                ]}}},
                {"$project": {
                    "present_w": _present_w_expr(),
                    "late_flag": _late_flag_expr(),
                    "late_m": {"$ifNull": ["$late_minutes", 0]},
                    "is_leave": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]},
                    "is_onduty": {"$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]},
                    "wh": {"$cond": [
                        {"$and": [{"$in": ["$status", PRESENCE]},
                                  {"$ne": ["$work_hours", None]}]},
                        "$work_hours", None]},
                }},
            ],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$department",
            "emp_codes": {"$addToSet": "$emp_code"},
            "present_days": {"$sum": {"$ifNull": ["$logs.present_w", 0.0]}},
            "wh_sum": {"$sum": {"$ifNull": ["$logs.wh", 0.0]}},
            # Count only real records with a value: a log-less employee's
            # unwind row has no $logs at all and must not dilute the mean.
            "wh_n": {"$sum": {"$cond": [
                {"$ne": [{"$ifNull": ["$logs.wh", None]}, None]}, 1, 0]}},
            "late_count": {"$sum": {"$ifNull": ["$logs.late_flag", 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$logs.late_m", 0]}},
            "leave_count": {"$sum": {"$ifNull": ["$logs.is_leave", 0]}},
            "on_duty_count": {"$sum": {"$ifNull": ["$logs.is_onduty", 0]}},
        }},
        {"$sort": {"_id": ASCENDING}},
    ]


def _leaderboard_pipeline(m_start: str, m_next: str,
                          department: Optional[str], limit: int) -> list:
    stages: list = [
        {"$match": {"date": {"$gte": m_start, "$lt": m_next}}},
        {"$group": {
            "_id": "$emp_code",
            "total": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "late_count": {"$sum": _late_flag_expr()},
        }},
        {"$match": {"total": {"$gt": 0}}},
        {"$sort": {"total": DESCENDING}},
        {"$lookup": {
            "from": "employees",
            "localField": "_id",
            "foreignField": "emp_code",
            "as": "emp",
        }},
        {"$unwind": "$emp"},
    ]
    if department:
        stages.append({"$match": {"emp.department": department}})
    stages += [
        {"$setWindowFields": {
            "sortBy": {"total": DESCENDING},
            "output": {"rank": {"$rank": {}}},
        }},
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"total": DESCENDING, "_id": ASCENDING}},
        {"$project": {
            "_id": 0,
            "rank": "$rank",
            "emp_code": "$_id",
            "name": "$emp.name",
            "department": "$emp.department",
            "total_late_minutes": "$total",
            "late_count": "$late_count",
        }},
    ]
    return stages


def _trend_pipeline(codes: list, joined: list, frm: str, to: str,
                    from_dt: datetime, to_excl: datetime) -> list:
    return [
        {"$match": {"emp_code": {"$in": codes},
                    "date": {"$gte": frm, "$lte": to}}},
        {"$group": {
            "_id": "$date",
            "present_count": {"$sum": {"$cond": [
                {"$in": ["$status", PRESENCE]},
                {"$cond": [{"$eq": [{"$ifNull": ["$half_day", False]}, True]}, 0.5, 1.0]},
                0.0]}},
            "late_count": {"$sum": _late_flag_expr()},
        }},
        {"$addFields": {"day": {"$dateFromString": {"dateString": "$_id"}}}},
        {"$densify": {"field": "day", "range": {
            "step": 1, "unit": "day", "bounds": [from_dt, to_excl]}}},
        {"$addFields": {
            "dayStr": {"$dateToString": {"format": "%Y-%m-%d", "date": "$day",
                                         "timezone": "Asia/Kolkata"}},
            "present_count": {"$ifNull": ["$present_count", 0.0]},
            "late_count": {"$ifNull": ["$late_count", 0]},
        }},
        {"$addFields": {
            "is_working_day": {"$and": [
                {"$gte": [{"$dayOfWeek": {"date": "$day",
                                          "timezone": "Asia/Kolkata"}}, 2]},
                {"$lte": [{"$dayOfWeek": {"date": "$day",
                                          "timezone": "Asia/Kolkata"}}, 6]}]},
            "headcount": {"$size": {"$filter": {
                "input": joined, "as": "j",
                "cond": {"$lte": ["$$j", "$dayStr"]}}}},
        }},
        {"$addFields": {
            "attendance_rate": {"$cond": [
                {"$and": ["$is_working_day", {"$gt": ["$headcount", 0]}]},
                {"$divide": [{"$trunc": {"$add": [
                    {"$multiply": [{"$divide": [
                        {"$toDecimal": "$present_count"},
                        {"$toDecimal": "$headcount"}]}, 10000]}, 0.5]}}, 10000]},
                None]},
        }},
        {"$setWindowFields": {
            "sortBy": {"day": ASCENDING},
            "output": {"_ma": {"$avg": "$attendance_rate",
                               "window": {"documents": [-6, 0]}}},
        }},
        {"$addFields": {
            "moving_avg_7d": {"$cond": [
                {"$eq": ["$_ma", None]}, None,
                {"$divide": [{"$trunc": {"$add": [
                    {"$multiply": [{"$toDecimal": "$_ma"}, 10000]}, 0.5]}}, 10000]}]},
        }},
        {"$sort": {"day": ASCENDING}},
        {"$project": {
            "_id": 0,
            "date": "$dayStr",
            "is_working_day": "$is_working_day",
            "headcount": "$headcount",
            "present_count": "$present_count",
            "late_count": "$late_count",
            "attendance_rate": {"$cond": [
                {"$eq": ["$attendance_rate", None]}, None,
                {"$toDouble": "$attendance_rate"}]},
            "moving_avg_7d": {"$cond": [
                {"$eq": ["$moving_avg_7d", None]}, None,
                {"$toDouble": "$moving_avg_7d"}]},
        }},
    ]


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str,
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    emp = db.employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(404, "unknown employee")
    m_start, m_next, m_end = _month_bounds(month)
    pipe = _monthly_pipeline(emp_code, m_start, m_next)
    rows = list(db.attendance_logs.aggregate(pipe))
    agg = rows[0] if rows else {}
    working_days = _working_days(month, emp.get("joined_on", m_start))
    present_days = float(agg.get("present_days", 0.0))
    attendance_pct = _round2(present_days / working_days * 100) if working_days else None
    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": int(agg.get("leave_days", 0)),
        "late_count": int(agg.get("late_count", 0)),
        "total_late_minutes": int(agg.get("total_late_minutes", 0)),
        "total_overtime_minutes": int(agg.get("total_overtime_minutes", 0)),
        "attendance_pct": attendance_pct,
    }


@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
):
    m_start, m_next, m_end = _month_bounds(month)
    emp_match: dict = {"joined_on": {"$lte": m_end}}
    if department:
        emp_match["department"] = department
    pipe = _dept_summary_pipeline(emp_match, m_start, m_next)
    items = []
    for r in db.employees.aggregate(pipe):
        if not r.get("emp_codes"):
            continue
        wh_n = int(r.get("wh_n", 0))
        items.append({
            "department": r["_id"],
            "headcount": len(r["emp_codes"]),
            "present_days": float(r.get("present_days", 0.0)),
            "avg_work_hours": _round2(Decimal(str(r["wh_sum"])) / wh_n) if wh_n else None,
            "late_count": int(r.get("late_count", 0)),
            "total_late_minutes": int(r.get("total_late_minutes", 0)),
            "leave_count": int(r.get("leave_count", 0)),
            "on_duty_count": int(r.get("on_duty_count", 0)),
        })
    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    m_start, m_next, _ = _month_bounds(month)
    stages = _leaderboard_pipeline(m_start, m_next, department, limit)
    items = list(db.attendance_logs.aggregate(stages))
    return {"month": month, "items": items}


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    frm: str = Query(alias="from"),
    to: str = Query(),
):
    _validate_date_str(frm, "from")
    _validate_date_str(to, "to")
    if to < frm:
        raise HTTPException(422, "to < from")
    d0, d1 = date_cls.fromisoformat(frm), date_cls.fromisoformat(to)
    if (d1 - d0).days > 91:
        raise HTTPException(422, "range exceeds 92 days")
    emps = list(db.employees.find({"department": department},
                                  {"_id": 0, "emp_code": 1, "joined_on": 1}))
    if not emps:
        raise HTTPException(404, "unknown department")
    codes = [e["emp_code"] for e in emps]
    joined = [e.get("joined_on", "0000-00-00") for e in emps]
    from_dt = datetime(d0.year, d0.month, d0.day)
    to_excl = datetime(d1.year, d1.month, d1.day) + timedelta(days=1)
    pipe = _trend_pipeline(codes, joined, frm, to, from_dt, to_excl)
    rows = list(db.attendance_logs.aggregate(pipe))
    return {"department": department, "items": [
        {"date": r["date"], "is_working_day": bool(r["is_working_day"]),
         "headcount": int(r["headcount"]),
         "present_count": float(r["present_count"]),
         "late_count": int(r["late_count"]),
         "attendance_rate": r["attendance_rate"],
         "moving_avg_7d": r["moving_avg_7d"]} for r in rows]}


@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str,
    emp_code: Optional[str] = None,
    month: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    frm: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    def _explain_find(coll: str, filt: dict, sort: dict,
                      skip: int = 0, lim: int = 0) -> dict:
        cmd: dict = {"find": coll, "filter": filt, "sort": sort}
        if skip:
            cmd["skip"] = skip
        if lim:
            cmd["limit"] = lim
        return db.command({"explain": cmd, "verbosity": "executionStats"})

    def _explain_agg(coll: str, pipeline: list) -> dict:
        return db.command({"explain": {"aggregate": coll, "pipeline": pipeline,
                                       "cursor": {}},
                           "verbosity": "executionStats"})

    def _ser(doc):
        return _json.loads(json_util.dumps(doc))

    if endpoint == "attendance_list":
        if date_from:
            _validate_date_str(date_from, "date_from")
        if date_to:
            _validate_date_str(date_to, "date_to")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "date_from > date_to")
        if status is not None and status not in (
                "PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"):
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
        raw = _explain_find("attendance_logs", q,
                            {"date": -1, "emp_code": 1},
                            (page - 1) * page_size, page_size)
        return {"endpoint": endpoint, "collection": "attendance_logs",
                "explain": _ser(raw)}

    if endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(422, "emp_code and month are required")
        _validate_month(month)
        m_start, m_next, _ = _month_bounds(month)
        pipe = _monthly_pipeline(emp_code, m_start, m_next)
        return {"endpoint": endpoint, "collection": "attendance_logs",
                "explain": _ser(_explain_agg("attendance_logs", pipe))}

    if endpoint == "department_summary":
        if not month:
            raise HTTPException(422, "month is required")
        _validate_month(month)
        _, m_next, m_end = _month_bounds(month)
        m_start = f"{month}-01"
        emp_match: dict = {"joined_on": {"$lte": m_end}}
        if department:
            emp_match["department"] = department
        pipe = _dept_summary_pipeline(emp_match, m_start, m_next)
        return {"endpoint": endpoint, "collection": "employees",
                "explain": _ser(_explain_agg("employees", pipe))}

    if endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(422, "month is required")
        _validate_month(month)
        m_start, m_next, _ = _month_bounds(month)
        pipe = _leaderboard_pipeline(m_start, m_next, department, limit)
        return {"endpoint": endpoint, "collection": "attendance_logs",
                "explain": _ser(_explain_agg("attendance_logs", pipe))}

    if endpoint == "department_trend":
        if not department or not frm or not to:
            raise HTTPException(422,
                                "department, from and to are required")
        _validate_date_str(frm, "from")
        _validate_date_str(to, "to")
        if to < frm:
            raise HTTPException(422, "to < from")
        d0, d1 = date_cls.fromisoformat(frm), date_cls.fromisoformat(to)
        if (d1 - d0).days > 91:
            raise HTTPException(422, "range exceeds 92 days")
        emps = list(db.employees.find({"department": department},
                                      {"_id": 0, "emp_code": 1, "joined_on": 1}))
        if not emps:
            raise HTTPException(404, "unknown department")
        codes = [e["emp_code"] for e in emps]
        joined = [e.get("joined_on", "0000-00-00") for e in emps]
        pipe = _trend_pipeline(
            codes, joined, frm, to,
            datetime(d0.year, d0.month, d0.day),
            datetime(d1.year, d1.month, d1.day) + timedelta(days=1))
        return {"endpoint": endpoint, "collection": "attendance_logs",
                "explain": _ser(_explain_agg("attendance_logs", pipe))}

    raise HTTPException(422, "unknown endpoint")
