// Base URL for the FastAPI backend. Override with a .env file:
//   VITE_API_BASE=http://127.0.0.1:8000
const API_BASE =
  import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

function qs(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

export function apiErrorMessage(err) {
  const d = err?.detail;
  if (Array.isArray(d)) {
    return d.map((e) => e?.msg || JSON.stringify(e)).join('; ');
  }
  if (typeof d === 'string') return d;
  return err?.message || 'Request failed';
}

async function req(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw { status: 0, detail: `Cannot reach API at ${API_BASE} (${e.message})` };
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw { status: res.status, detail: data?.detail ?? `HTTP ${res.status}` };
  }
  return data;
}

export const api = {
  health: () => req('/health'),
  listEmployees: (p) => req(`/employees${qs(p)}`),
  createEmployee: (b) => req('/employees', { method: 'POST', body: b }),
  listAttendance: (p) => req(`/attendance${qs(p)}`),
  punchIn: (b) => req('/attendance/punch-in', { method: 'POST', body: b }),
  punchOut: (b) => req('/attendance/punch-out', { method: 'POST', body: b }),
  regularize: (emp, date, b) =>
    req(`/attendance/${encodeURIComponent(emp)}/${encodeURIComponent(date)}`, {
      method: 'PATCH',
      body: b,
    }),
  monthly: (emp, month) =>
    req(`/analytics/employees/${encodeURIComponent(emp)}/monthly${qs({ month })}`),
  deptSummary: (p) => req(`/analytics/departments/summary${qs(p)}`),
  leaderboard: (p) => req(`/analytics/leaderboard/late${qs(p)}`),
  trend: (dept, p) =>
    req(`/analytics/departments/${encodeURIComponent(dept)}/trend${qs(p)}`),
};

// Epoch millis -> IST string for display. Null/undefined -> em dash.
export function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(ms));
}

// "datetime-local" input value -> epoch millis (local wall time), or undefined.
export function localToMs(v) {
  if (!v) return undefined;
  const t = new Date(v).getTime();
  return Number.isNaN(t) ? undefined : t;
}

// Epoch millis -> "datetime-local" input value (for prefilling forms).
export function msToLocal(ms) {
  if (ms === null || ms === undefined) return '';
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
