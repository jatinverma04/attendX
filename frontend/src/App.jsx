import { useCallback, useEffect, useState } from 'react';
import { api, apiErrorMessage, fmtMs, localToMs } from './api.js';
import './App.css';

const TABS = ['Employees', 'Attendance', 'Punch', 'Analytics'];
const ANALYTICS_TABS = ['Monthly', 'Departments', 'Leaderboard', 'Trend'];

function useAsync() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const run = useCallback(async (fn) => {
    setLoading(true);
    setError('');
    try {
      return await fn();
    } catch (e) {
      setError(apiErrorMessage(e));
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);
  return { loading, error, setError, run };
}

function Banner({ error, loading, empty, emptyText }) {
  if (loading) return <p className="state">Loading…</p>;
  if (error) return <p className="state error">Error: {error}</p>;
  if (empty) return <p className="state">{emptyText || 'No records found.'}</p>;
  return null;
}

function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Prev</button>
      <span>Page {page} of {pages} · {total} total</span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next ›</button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

/* ---------------- Employees ---------------- */
function Employees() {
  const { loading, error, run } = useAsync();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [dept, setDept] = useState('');
  const [page, setPage] = useState(1);
  const [msg, setMsg] = useState('');
  const [form, setForm] = useState({ emp_code: '', name: '', email: '', department: '', shift_start: '09:30', shift_end: '18:30', joined_on: '' });
  const pageSize = 20;

  const load = useCallback((p = 1, d = dept) => {
    setPage(p);
    return run(async () => {
      const r = await api.listEmployees({ department: d || undefined, page: p, page_size: pageSize });
      setItems(r.items);
      setTotal(r.total);
    });
  }, [dept, run]);

  useEffect(() => { load(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (e) => {
    e.preventDefault();
    setMsg('');
    const r = await run(() => api.createEmployee(form));
    if (r) {
      setMsg(`Created ${r.emp_code}.`);
      setForm({ emp_code: '', name: '', email: '', department: '', shift_start: '09:30', shift_end: '18:30', joined_on: '' });
      load(1);
    }
  };

  return (
    <section>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); load(1); }}>
        <Field label="Department filter">
          <input value={dept} onChange={(e) => setDept(e.target.value)} placeholder="Engineering" />
        </Field>
        <button type="submit">Search</button>
      </form>
      <Banner loading={loading} error={error} empty={!loading && !error && items.length === 0} />
      {items.length > 0 && (
        <>
          <table>
            <thead><tr><th>Code</th><th>Name</th><th>Email</th><th>Dept</th><th>Shift</th><th>Joined</th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.emp_code}>
                  <td><code>{x.emp_code}</code></td><td>{x.name}</td><td>{x.email}</td>
                  <td>{x.department}</td><td>{x.shift_start}–{x.shift_end}</td><td>{x.joined_on}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} pageSize={pageSize} total={total} onPage={(p) => load(p)} />
        </>
      )}
      <h3>Add employee</h3>
      {msg && <p className="state ok">{msg}</p>}
      <form className="grid" onSubmit={create}>
        {['emp_code', 'name', 'email', 'department'].map((k) => (
          <Field key={k} label={k}><input required value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
        ))}
        <Field label="shift_start"><input required pattern="^([01]\d|2[0-3]):[0-5]\d$" value={form.shift_start} onChange={(e) => setForm({ ...form, shift_start: e.target.value })} /></Field>
        <Field label="shift_end"><input required pattern="^([01]\d|2[0-3]):[0-5]\d$" value={form.shift_end} onChange={(e) => setForm({ ...form, shift_end: e.target.value })} /></Field>
        <Field label="joined_on"><input required type="date" value={form.joined_on} onChange={(e) => setForm({ ...form, joined_on: e.target.value })} /></Field>
        <button type="submit">Create</button>
      </form>
    </section>
  );
}

/* ---------------- Attendance + regularization ---------------- */
function Attendance() {
  const { loading, error, run } = useAsync();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [f, setF] = useState({ emp_code: '', date_from: '', date_to: '', status: '' });
  const [reg, setReg] = useState(null); // {emp_code, date}
  const [rform, setRform] = useState({ status: '', punch_in: '', punch_out: '', reason: '', regularized_by: '' });
  const [rmsg, setRmsg] = useState('');
  const pageSize = 20;

  const load = useCallback((p = 1) => {
    setPage(p);
    return run(async () => {
      const r = await api.listAttendance({ ...f, page: p, page_size: pageSize });
      setItems(r.items);
      setTotal(r.total);
    });
  }, [f, run]);

  useEffect(() => { load(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openReg = (row) => {
    setReg({ emp_code: row.emp_code, date: row.date });
    setRform({ status: '', punch_in: localToMs(row.punch_in), punch_out: localToMs(row.punch_out), reason: '', regularized_by: '' });
    setRmsg('');
  };

  const submitReg = async (e) => {
    e.preventDefault();
    setRmsg('');
    const body = { reason: rform.reason, regularized_by: rform.regularized_by };
    if (rform.status) body.status = rform.status;
    const pi = localToMs(rform.punch_in);
    const po = localToMs(rform.punch_out);
    if (pi !== undefined) body.punch_in = pi;
    if (po !== undefined) body.punch_out = po;
    const r = await run(() => api.regularize(reg.emp_code, reg.date, body));
    if (r) {
      setRmsg('Correction saved.');
      load(page);
    }
  };

  return (
    <section>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); load(1); }}>
        <Field label="emp_code"><input value={f.emp_code} onChange={(e) => setF({ ...f, emp_code: e.target.value })} /></Field>
        <Field label="date_from"><input type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
        <Field label="date_to"><input type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
        <Field label="status">
          <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="">(any)</option>
            {['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <button type="submit">Search</button>
      </form>
      <Banner loading={loading} error={error} empty={!loading && !error && items.length === 0} />
      {items.length > 0 && (
        <>
          <table>
            <thead><tr><th>Date</th><th>Code</th><th>Status</th><th>In (IST)</th><th>Out (IST)</th><th>Hrs</th><th>Late</th><th>OT</th><th>½</th><th></th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={`${x.emp_code}${x.date}`}>
                  <td>{x.date}</td><td><code>{x.emp_code}</code></td><td>{x.status}</td>
                  <td>{fmtMs(x.punch_in)}</td><td>{fmtMs(x.punch_out)}</td>
                  <td>{x.work_hours ?? '—'}</td><td>{x.late_minutes}</td>
                  <td>{x.overtime_minutes}</td><td>{x.half_day ? 'yes' : 'no'}</td>
                  <td><button type="button" onClick={() => openReg(x)}>Fix</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} pageSize={pageSize} total={total} onPage={(p) => load(p)} />
        </>
      )}
      {reg && (
        <div className="card">
          <h3>Regularize {reg.emp_code} / {reg.date}</h3>
          {rmsg && <p className="state ok">{rmsg}</p>}
          <form className="grid" onSubmit={submitReg}>
            <Field label="status (omit = unchanged)">
              <select value={rform.status} onChange={(e) => setRform({ ...rform, status: e.target.value })}>
                <option value="">(unchanged)</option>
                {['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="punch_in"><input type="datetime-local" value={rform.punch_in} onChange={(e) => setRform({ ...rform, punch_in: e.target.value })} /></Field>
            <Field label="punch_out"><input type="datetime-local" value={rform.punch_out} onChange={(e) => setRform({ ...rform, punch_out: e.target.value })} /></Field>
            <Field label="reason (min 5 chars)"><input required minLength={5} maxLength={200} value={rform.reason} onChange={(e) => setRform({ ...rform, reason: e.target.value })} /></Field>
            <Field label="regularized_by"><input required maxLength={50} value={rform.regularized_by} onChange={(e) => setRform({ ...rform, regularized_by: e.target.value })} /></Field>
            <button type="submit">Save correction</button>
            <button type="button" onClick={() => setReg(null)}>Close</button>
          </form>
        </div>
      )}
    </section>
  );
}

/* ---------------- Punch ---------------- */
function Punch() {
  const { loading, error, run } = useAsync();
  const [result, setResult] = useState(null);
  const [iForm, setIForm] = useState({ emp_code: '', at: '', status: 'PRESENT' });
  const [oForm, setOForm] = useState({ emp_code: '', at: '' });

  const punchIn = async (e) => {
    e.preventDefault();
    const body = { emp_code: iForm.emp_code, status: iForm.status };
    const t = localToMs(iForm.at);
    if (t !== undefined) body.punched_at = t;
    const r = await run(() => api.punchIn(body));
    if (r) setResult({ kind: 'punch-in', row: r });
  };
  const punchOut = async (e) => {
    e.preventDefault();
    const body = { emp_code: oForm.emp_code };
    const t = localToMs(oForm.at);
    if (t !== undefined) body.punched_at = t;
    const r = await run(() => api.punchOut(body));
    if (r) setResult({ kind: 'punch-out', row: r });
  };

  return (
    <section className="two">
      <div className="card">
        <h3>Punch in</h3>
        <form className="grid" onSubmit={punchIn}>
          <Field label="emp_code"><input required value={iForm.emp_code} onChange={(e) => setIForm({ ...iForm, emp_code: e.target.value })} /></Field>
          <Field label="at (omit = now)"><input type="datetime-local" value={iForm.at} onChange={(e) => setIForm({ ...iForm, at: e.target.value })} /></Field>
          <Field label="status">
            <select value={iForm.status} onChange={(e) => setIForm({ ...iForm, status: e.target.value })}>
              {['PRESENT', 'WFH', 'ON_DUTY'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <button type="submit">Punch in</button>
        </form>
      </div>
      <div className="card">
        <h3>Punch out</h3>
        <form className="grid" onSubmit={punchOut}>
          <Field label="emp_code"><input required value={oForm.emp_code} onChange={(e) => setOForm({ ...oForm, emp_code: e.target.value })} /></Field>
          <Field label="at (omit = now)"><input type="datetime-local" value={oForm.at} onChange={(e) => setOForm({ ...oForm, at: e.target.value })} /></Field>
          <button type="submit">Punch out</button>
        </form>
      </div>
      <div className="wide">
        <Banner loading={loading} error={error} />
        {result && !loading && !error && (
          <table>
            <thead><tr><th>Action</th><th>Date</th><th>Code</th><th>Status</th><th>In</th><th>Out</th><th>Hrs</th><th>Late</th><th>OT</th></tr></thead>
            <tbody><tr>
              <td>{result.kind}</td><td>{result.row.date}</td><td><code>{result.row.emp_code}</code></td>
              <td>{result.row.status}</td><td>{fmtMs(result.row.punch_in)}</td><td>{fmtMs(result.row.punch_out)}</td>
              <td>{result.row.work_hours ?? '—'}</td><td>{result.row.late_minutes}</td><td>{result.row.overtime_minutes}</td>
            </tr></tbody>
          </table>
        )}
      </div>
    </section>
  );
}

/* ---------------- Analytics ---------------- */
function Monthly() {
  const { loading, error, run } = useAsync();
  const [emp, setEmp] = useState('');
  const [month, setMonth] = useState('2026-07');
  const [data, setData] = useState(null);
  const go = async (e) => {
    e?.preventDefault();
    const r = await run(() => api.monthly(emp, month));
    if (r) setData(r);
  };
  return (
    <section>
      <form className="filters" onSubmit={go}>
        <Field label="emp_code"><input required value={emp} onChange={(e) => setEmp(e.target.value)} placeholder="EMP0001" /></Field>
        <Field label="month"><input required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} placeholder="2026-07" /></Field>
        <button type="submit">Run</button>
      </form>
      <Banner loading={loading} error={error} />
      {data && !loading && !error && (
        <dl className="stats">
          {['working_days', 'present_days', 'leave_days', 'late_count', 'total_late_minutes', 'total_overtime_minutes', 'attendance_pct'].map((k) => (
            <div key={k}><dt>{k}</dt><dd>{data[k] ?? '—'}</dd></div>
          ))}
        </dl>
      )}
    </section>
  );
}

function Departments() {
  const { loading, error, run } = useAsync();
  const [month, setMonth] = useState('2026-07');
  const [dept, setDept] = useState('');
  const [items, setItems] = useState(null);
  const go = async (e) => {
    e?.preventDefault();
    const r = await run(() => api.deptSummary({ month, department: dept || undefined }));
    if (r) setItems(r.items);
  };
  return (
    <section>
      <form className="filters" onSubmit={go}>
        <Field label="month"><input required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
        <Field label="department (optional)"><input value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <button type="submit">Run</button>
      </form>
      <Banner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <table>
          <thead><tr><th>Dept</th><th>Headcount</th><th>Present</th><th>Avg hrs</th><th>Late n</th><th>Late min</th><th>Leave</th><th>On duty</th></tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.department}>
                <td>{x.department}</td><td>{x.headcount}</td><td>{x.present_days}</td>
                <td>{x.avg_work_hours ?? '—'}</td><td>{x.late_count}</td>
                <td>{x.total_late_minutes}</td><td>{x.leave_count}</td><td>{x.on_duty_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Leaderboard() {
  const { loading, error, run } = useAsync();
  const [month, setMonth] = useState('2026-07');
  const [limit, setLimit] = useState(10);
  const [dept, setDept] = useState('');
  const [items, setItems] = useState(null);
  const max = items?.reduce((m, x) => Math.max(m, x.total_late_minutes), 0) || 1;
  const go = async (e) => {
    e?.preventDefault();
    const r = await run(() => api.leaderboard({ month, limit, department: dept || undefined }));
    if (r) setItems(r.items);
  };
  return (
    <section>
      <form className="filters" onSubmit={go}>
        <Field label="month"><input required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
        <Field label="limit"><input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></Field>
        <Field label="department (optional)"><input value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <button type="submit">Run</button>
      </form>
      <Banner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <table>
          <thead><tr><th>Rank</th><th>Code</th><th>Name</th><th>Dept</th><th>Late min</th><th>Late n</th><th></th></tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.emp_code}>
                <td>#{x.rank}</td><td><code>{x.emp_code}</code></td><td>{x.name}</td>
                <td>{x.department}</td><td>{x.total_late_minutes}</td><td>{x.late_count}</td>
                <td className="bar-cell"><div className="bar" style={{ width: `${(x.total_late_minutes / max) * 100}%` }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Trend() {
  const { loading, error, run } = useAsync();
  const [dept, setDept] = useState('');
  const [from, setFrom] = useState('2026-07-01');
  const [to, setTo] = useState('2026-07-07');
  const [items, setItems] = useState(null);
  const max = items?.reduce((m, x) => Math.max(m, x.attendance_rate ?? 0), 0) || 1;
  const go = async (e) => {
    e?.preventDefault();
    const r = await run(() => api.trend(dept, { from, to }));
    if (r) setItems(r.items);
  };
  return (
    <section>
      <form className="filters" onSubmit={go}>
        <Field label="department"><input required value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <Field label="from"><input required type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="to"><input required type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <button type="submit">Run</button>
      </form>
      <Banner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <table>
          <thead><tr><th>Date</th><th>Workday</th><th>Headcount</th><th>Present</th><th>Late</th><th>Rate</th><th>7d avg</th><th></th></tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.date} className={x.is_working_day ? '' : 'weekend'}>
                <td>{x.date}</td><td>{x.is_working_day ? 'yes' : 'no'}</td><td>{x.headcount}</td>
                <td>{x.present_count}</td><td>{x.late_count}</td>
                <td>{x.attendance_rate ?? '—'}</td><td>{x.moving_avg_7d ?? '—'}</td>
                <td className="bar-cell"><div className="bar" style={{ width: `${((x.attendance_rate ?? 0) / max) * 100}%` }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Analytics() {
  const [sub, setSub] = useState('Monthly');
  return (
    <section>
      <nav className="subtabs">
        {ANALYTICS_TABS.map((t) => (
          <button key={t} type="button" className={sub === t ? 'active' : ''} onClick={() => setSub(t)}>{t}</button>
        ))}
      </nav>
      {sub === 'Monthly' && <Monthly />}
      {sub === 'Departments' && <Departments />}
      {sub === 'Leaderboard' && <Leaderboard />}
      {sub === 'Trend' && <Trend />}
    </section>
  );
}

/* ---------------- App ---------------- */
export default function App() {
  const [tab, setTab] = useState('Employees');
  const [health, setHealth] = useState('');
  useEffect(() => {
    api.health().then(() => setHealth('ok')).catch((e) => setHealth(apiErrorMessage(e)));
  }, []);
  return (
    <div className="app">
      <header>
        <h1>AttendX</h1>
        <p className="health">API: {health === 'ok' ? 'connected' : health || 'checking…'}</p>
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t} type="button" className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <main>
        {tab === 'Employees' && <Employees />}
        {tab === 'Attendance' && <Attendance />}
        {tab === 'Punch' && <Punch />}
        {tab === 'Analytics' && <Analytics />}
      </main>
    </div>
  );
}
