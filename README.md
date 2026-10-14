# AttendX — Employee Attendance & Analytics API

FastAPI + MongoDB backend (`backend/app/main.py`) with a React + Vite dashboard (`frontend/`).

## Run from a clean clone (repository root)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Configure MongoDB via environment (a local `backend/.env` also works;
real environment variables take priority — never commit `.env`):

```bash
# Windows (PowerShell): $env:MONGO_URI="..."; $env:MONGO_DB="..."
# macOS/Linux: export MONGO_URI="..." MONGO_DB="..."
```

Optional sample data, then start (repository root):

```bash
python backend/sample_seed.py
python -m uvicorn app.main:app --port 8000
```

`GET /health` returns `{"status": "ok"}` once MongoDB answers its ping.
Frontend dev server (separate terminal, from `frontend/`): `npm install`
once, then `npm run dev`, with `VITE_API_BASE` pointing at the API.

Contract: `backend/openapi.yaml` (rules R1–R10). Storage: `backend/DATA_MODEL.md`.
Starter review: `backend/REVIEW.md`. Index/design notes: `backend/DECISIONS.md`.
