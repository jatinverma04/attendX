# REVIEW.md

PROBLEM_STATEMENT.docx found at `PROBLEM_STATEMENT.docx`; no requirement had to be guessed.

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `compute_late_minutes` | `minutes > 10` on minute-truncated delta; misses R2 "strictly more than 10:00" with floor-from-shift-start | `shift 09:30`, punch `09:40:01` → returned `0`, expected `10` | Compare seconds `diff <= 600 → 0` else `floor(diff/60)` on truncated IST instants |
| 2 | `compute_work_hours` | `round()` = banker's rounding, not R4/R8 half-up | `3618s → 1.005h` returned `1.0`, expected `1.01` | `Decimal(...).quantize(0.01, ROUND_HALF_UP)` |
| 3 | `compute_overtime` | No 30-min gate (R3); naive `fromisoformat(date)` end; overnight shift end not moved to next day | `punch_out = shift_end+5m` returned `5`, expected `0` | `floor` diff vs IST shift-end (+1 day when `shift_end <= shift_start`); `<30 → 0` |
| 4 | `GET /health` | Always `200`; never pings Mongo | Kill Mongo → still `200`, expected `503` | `client.admin.command("ping")`, `503` on failure |
| 5 | `POST /employees` validation | All fields plain `str`; no pattern/length checks | `emp_code=BAD`, `email=bad`, `shift 25:00`, `start==end` all `201`, expected `422` | `EMP\d{4,6}`, email regex, `HH:MM` patterns, `joined_on` date check, `start != end` validator |
| 6 | `POST /employees` `created_at` | `datetime.now()` naive-local, returned as ISO string | Response `created_at` is string, expected epoch-ms int | `now(UTC)` truncated; serialize to ms; strip `_id` |
| 7 | `POST /employees` uniqueness | `find_one` + `insert` race, no unique index | Parallel duplicate `emp_code` → two `201` | Unique index `employees(emp_code)`; `DuplicateKeyError → 409` |
| 8 | `GET /employees` paging | `skip = page*page_size` | `page=1` skips first 20 rows | `(page-1)*page_size` |
| 9 | `GET /employees` total/sort | `count_documents({})` ignores filter; no sort; no `page_size ≤ 100` | `?department=X` returns whole-collection `total`; unordered | Count with same `q`; `sort emp_code asc`; `Query(ge/le)` |
| 10 | `POST /attendance/punch-in` unknown emp | `emp["shift_start"]` on `None` → `500` | `emp_code=EMP9999` → `500`, expected `404` | Explicit `404` |
| 11 | `POST /attendance/punch-in` body | `status: str`, `punched_at: int` unconstrained | `status=ABSENT`, `punched_at=123` (seconds) accepted, expected `422` | `status ∈ PRESENT/WFH/ON_DUTY`; strict `EpochMillis 1e11..4102444800000` |
| 12 | `POST /attendance/punch-in` date/tz | `fromtimestamp()` server-local naive + `ts.date()`; no truncation, no overnight rule | `00:30 IST` with `22:00-06:00` shift filed under wrong `date` | ms → UTC → truncate sec → IST date; `IST time < shift_end → date-1` for overnight |
| 13 | `POST /attendance/punch-in` race/shape | Check-then-insert; returns `id=str(_id)`, raw datetimes | Parallel double punch-in → two `201`; response has `id`, ISO dates | Unique index `(emp_code,date)` + `409`; strip `_id`/`id`; BSON→epoch-ms incl. history |
| 14 | `GET /attendance` scale/sort | `list(find(q))` + Python sort/slice; sorts date only | ~100k records loaded into memory; same-date order wrong | Mongo `sort(date desc, emp_code asc)` + `skip/limit`; `count_documents(q)` |
| 15 | `GET /attendance` validation/shape | No `date_from>date_to → 422`, free `status`, adds `id`, raw datetimes | `date_from=2026-02-01&date_to=2026-01-01` → `200`, expected `422` | Date validation, status enum, exact `AttendanceRecord` serialization |
| 16 | Indexes | None created at startup | Fresh DB allows duplicate `emp_code` / `(emp_code,date)`; explain shows `COLLSCAN` | Idempotent startup: unique `employees(emp_code)`, unique `logs(emp_code,date)`, `logs(date,emp_code)`, `employees(department,emp_code)`; index errors swallowed at import so `/health` can still report `503`, retried on startup |

Inspected but **not** defects: `load_dotenv()` default (env vars already win — matches "real environment variables must win"); `PunchInIn.status` default `PRESENT` (per contract); punch-in defaults `punch_out=null/work_hours=null/overtime=0/half_day=false/history=[]` (per DATA_MODEL.md §3); `list_*` default `page=1, page_size=20` (R10).
