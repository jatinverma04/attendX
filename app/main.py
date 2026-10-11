"""Root entry point for `uvicorn app.main:app --port 8000` run from the repo root.

Single source of truth stays in `backend/app/main.py`; this file only
re-exports its FastAPI `app` (loaded from that exact file path so there is
exactly one copy of the application logic).
"""
import importlib.util
import sys
from pathlib import Path

_BACKEND_MAIN = Path(__file__).resolve().parent.parent / "backend" / "app" / "main.py"

_spec = importlib.util.spec_from_file_location("_attendx_backend_main", _BACKEND_MAIN)
_backend = importlib.util.module_from_spec(_spec)
sys.modules["_attendx_backend_main"] = _backend
_spec.loader.exec_module(_backend)

app = _backend.app
