# AttendX — Employee Attendance & Analytics API

FastAPI + MongoDB service. All application code is `app/main.py`.

## Run (from `backend/`)

```bash
pip install -r requirements.txt
cp .env.example .env   # set MONGO_URI and MONGO_DB
python sample_seed.py  # optional sample data
uvicorn app.main:app --port 8000
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
