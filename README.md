# AttendX — Employee Attendance & Analytics API

FastAPI + MongoDB backend (`app/main.py`) with a React + Vite dashboard (`frontend/`).

## Run from a clean clone (repository root)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Configure MongoDB via environment (a local `.env` also works;
real environment variables take priority — never commit `.env`):

| Variable | Meaning |
|---|---|
| `MONGO_URI` | MongoDB connection string (env vars win over `.env`) |
| `MONGO_DB` | Database name |

```bash
# Windows (PowerShell): $env:MONGO_URI="..."; $env:MONGO_DB="..."
# macOS/Linux: export MONGO_URI="..." MONGO_DB="..."
```

Optional sample data, then start (repository root):

```bash
python sample_seed.py
python -m uvicorn app.main:app --port 8000
```

`GET /health` returns `{"status": "ok"}` (200) once MongoDB answers its ping and
503 otherwise. Indexes are created at startup, idempotently.

Frontend dev server (separate terminal, from `frontend/`): `npm install`
once, then `npm run dev`, with `VITE_API_BASE` pointing at the API.

## Testing

Backend regression suite (isolated `attendx_pytest` database, never seed data):

```bash
pip install -r requirements-test.txt
python -m pytest tests/ -q   # from the repository root, with MONGO_URI set
```

Frontend browser suite (needs the API on `:8000` with seed data):

```bash
cd frontend && npm run test:e2e   # starts the vite dev server automatically
```

## Docs

Contract: `openapi.yaml` (rules R1–R10). Storage: `DATA_MODEL.md`.
Starter review: `REVIEW.md`. Index/design notes: `DECISIONS.md`.
