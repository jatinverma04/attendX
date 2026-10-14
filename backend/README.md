# AttendX — Employee Attendance & Analytics API

FastAPI + MongoDB service. All application code is `app/main.py`.

## Run (from `backend/`)

```bash
pip install -r requirements.txt
cp .env.example .env   # set MONGO_URI and MONGO_DB
python sample_seed.py  # optional sample data
python -m uvicorn app.main:app --port 8000
```

## Environment

| Variable | Meaning |
|---|---|
| `MONGO_URI` | MongoDB connection string (env vars win over `.env`) |
| `MONGO_DB` | Database name |

Indexes are created at startup, idempotently. `GET /health` returns 200 only when MongoDB answers a ping.

## Implemented

Employees, punch-in/out, regularization with history, attendance listing,
monthly/department/leaderboard/trend analytics (aggregation pipelines),
and `GET /admin/explain/{endpoint}`. Contract: `openapi.yaml` (rules R1–R10);
storage: `DATA_MODEL.md`; starter defects: `REVIEW.md`; index/design notes: `DECISIONS.md`.

## Testing

Backend regression suite (isolated `attendx_pytest` database, never seed data):

```bash
pip install -r requirements-test.txt
python -m pytest tests/ -q   # run from backend/ with MONGO_URI set
```

Frontend browser suite (needs the API on `:8000` with seed data):

```bash
npm run test:e2e   # from frontend/; starts vite dev automatically
```
