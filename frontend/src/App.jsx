import { useCallback, useEffect, useState } from 'react';
import {
  BarChart3,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock,
  Inbox,
  Loader2,
  Monitor,
  Moon,
  Plus,
  RefreshCw,
  Search,
  Sun,
  TriangleAlert,
  Trophy,
  TrendingUp,
  UserCheck,
  Users,
  Wifi,
  WifiOff,
  Wrench,
  X,
} from 'lucide-react';
import { api, apiErrorMessage, fmtMs, localToMs } from './api.js';
import { useTheme } from './theme.js';

/* ---------- shared styles ---------- */
const inputCls =
  'h-10 w-full rounded-lg border border-line2 bg-white px-3 text-sm text-ink placeholder:text-mist dark:border-edg dark:bg-elev dark:text-bone dark:placeholder:text-fog';
const btnPrimary =
  'inline-flex h-10 items-center gap-2 rounded-lg bg-olive-600 px-4 text-sm font-medium text-white hover:bg-olive-700 disabled:opacity-50';
const btnGhost =
  'inline-flex h-10 items-center gap-2 rounded-lg border border-line2 bg-white px-4 text-sm font-medium text-smoke hover:bg-cream disabled:opacity-50 dark:border-edg dark:bg-elev dark:text-bone dark:hover:bg-elev2';
const btnSm =
  'inline-flex h-8 items-center gap-1 rounded-md border border-line2 bg-white px-2.5 text-xs font-medium text-smoke hover:bg-cream disabled:opacity-50 dark:border-edg dark:bg-elev dark:text-bone dark:hover:bg-elev2';
const tabCls = (active) =>
  `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
    active
      ? 'bg-olive-100 text-olive-700 dark:bg-olive-700/20 dark:text-olive-200'
      : 'text-fog hover:bg-wash/60 dark:text-ash dark:hover:bg-elev2'
  }`;

const STATUS_STYLE = {
  PRESENT: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  WFH: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  ON_DUTY: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  ABSENT: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  LEAVE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
};

function StatusBadge({ value }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[value] || 'bg-wash text-smoke dark:bg-elev2 dark:text-bone'}`}
    >
      {value}
    </span>
  );
}

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
  return { loading, error, run };
}

function StateBanner({ loading, error, empty, emptyText }) {
  if (loading)
    return (
      <p className="flex items-center gap-2 rounded-lg border border-line px-4 py-3 text-sm text-fog dark:border-edg dark:text-ash">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading…
      </p>
    );
  if (error)
    return (
      <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> Error: {error}
      </p>
    );
  if (empty)
    return (
      <p className="flex items-center gap-2 rounded-lg border border-dashed border-line2 px-4 py-3 text-sm text-fog dark:border-edg dark:text-ash">
        <Inbox className="h-4 w-4" aria-hidden /> {emptyText || 'No records found.'}
      </p>
    );
  return null;
}

function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center gap-3 text-sm text-fog dark:text-ash">
      <button type="button" className={btnSm} disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
        <ChevronLeft className="h-4 w-4" aria-hidden /> Prev
      </button>
      <span>Page {page} of {pages} · {total} total</span>
      <button type="button" className={btnSm} disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
        Next <ChevronRight className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-fog dark:text-ash">
      {label}
      {children}
    </label>
  );
}

function Card({ title, icon: Icon, children, action }) {
  return (
    <section className="rounded-xl border border-line bg-white p-4 shadow-sm sm:p-5 dark:border-edg dark:bg-elev">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold text-ink dark:text-bone">
          {Icon && <Icon className="h-4 w-4 text-olive-600 dark:text-olive-200" aria-hidden />}
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function TableWrap({ children }) {
  return <div className="overflow-x-auto rounded-lg border border-line dark:border-edg">{children}</div>;
}

const thCls =
  'whitespace-nowrap bg-wash px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-fog dark:bg-elev2/60 dark:text-ash';
const tdCls = 'whitespace-nowrap px-3 py-2 text-sm text-smoke dark:text-bone';

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
    <div className="flex flex-col gap-4">
      <Card title="Employees" icon={Users}>
        <form className="mb-3 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); load(1); }}>
          <Field label="Department filter">
            <input className={inputCls} value={dept} onChange={(e) => setDept(e.target.value)} placeholder="Engineering" />
          </Field>
          <button type="submit" className={btnPrimary}><Search className="h-4 w-4" aria-hidden /> Search</button>
        </form>
        <StateBanner loading={loading} error={error} empty={!loading && !error && items.length === 0} />
        {items.length > 0 && (
          <div className="flex flex-col gap-3">
            <TableWrap>
              <table className="w-full border-collapse">
                <thead><tr><th className={thCls}>Code</th><th className={thCls}>Name</th><th className={thCls}>Email</th><th className={thCls}>Dept</th><th className={thCls}>Shift</th><th className={thCls}>Joined</th></tr></thead>
                <tbody>
                  {items.map((x) => (
                    <tr key={x.emp_code} className="border-t border-line hover:bg-wash dark:border-edg dark:hover:bg-elev2/50">
                      <td className={tdCls}><code className="rounded bg-cream px-1.5 py-0.5 font-mono text-xs dark:bg-elev2">{x.emp_code}</code></td>
                      <td className={tdCls}>{x.name}</td><td className={tdCls}>{x.email}</td>
                      <td className={tdCls}>{x.department}</td><td className={tdCls}>{x.shift_start}–{x.shift_end}</td><td className={tdCls}>{x.joined_on}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <Pager page={page} pageSize={pageSize} total={total} onPage={(p) => load(p)} />
          </div>
        )}
      </Card>
      <Card title="Add employee" icon={Plus}>
        {msg && <p className="mb-3 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">{msg}</p>}
        <form className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={create}>
          {['emp_code', 'name', 'email', 'department'].map((k) => (
            <Field key={k} label={k}><input className={inputCls} required value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
          ))}
          <Field label="shift_start"><input className={inputCls} required pattern="^([01]\d|2[0-3]):[0-5]\d$" value={form.shift_start} onChange={(e) => setForm({ ...form, shift_start: e.target.value })} /></Field>
          <Field label="shift_end"><input className={inputCls} required pattern="^([01]\d|2[0-3]):[0-5]\d$" value={form.shift_end} onChange={(e) => setForm({ ...form, shift_end: e.target.value })} /></Field>
          <Field label="joined_on"><input className={inputCls} required type="date" value={form.joined_on} onChange={(e) => setForm({ ...form, joined_on: e.target.value })} /></Field>
          <div className="sm:col-span-2 lg:col-span-4"><button type="submit" className={btnPrimary}><Plus className="h-4 w-4" aria-hidden /> Create</button></div>
        </form>
      </Card>
    </div>
  );
}

/* ---------------- Attendance + regularization ---------------- */
function Attendance() {
  const { loading, error, run } = useAsync();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [f, setF] = useState({ emp_code: '', date_from: '', date_to: '', status: '' });
  const [reg, setReg] = useState(null);
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
    <div className="flex flex-col gap-4">
      <Card title="Attendance records" icon={ClipboardList}>
        <form className="mb-3 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); load(1); }}>
          <Field label="emp_code"><input className={inputCls} value={f.emp_code} onChange={(e) => setF({ ...f, emp_code: e.target.value })} /></Field>
          <Field label="date_from"><input className={inputCls} type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
          <Field label="date_to"><input className={inputCls} type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
          <Field label="status">
            <select className={inputCls} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              <option value="">(any)</option>
              {['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <button type="submit" className={btnPrimary}><Search className="h-4 w-4" aria-hidden /> Search</button>
        </form>
        <StateBanner loading={loading} error={error} empty={!loading && !error && items.length === 0} />
        {items.length > 0 && (
          <div className="flex flex-col gap-3">
            <TableWrap>
              <table className="w-full border-collapse">
                <thead><tr><th className={thCls}>Date</th><th className={thCls}>Code</th><th className={thCls}>Status</th><th className={thCls}>In (IST)</th><th className={thCls}>Out (IST)</th><th className={thCls}>Hrs</th><th className={thCls}>Late</th><th className={thCls}>OT</th><th className={thCls}>½</th><th className={thCls}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {items.map((x) => (
                    <tr key={`${x.emp_code}${x.date}`} className="border-t border-line hover:bg-wash dark:border-edg dark:hover:bg-elev2/50">
                      <td className={tdCls}>{x.date}</td>
                      <td className={tdCls}><code className="rounded bg-cream px-1.5 py-0.5 font-mono text-xs dark:bg-elev2">{x.emp_code}</code></td>
                      <td className={tdCls}><StatusBadge value={x.status} /></td>
                      <td className={tdCls}>{fmtMs(x.punch_in)}</td><td className={tdCls}>{fmtMs(x.punch_out)}</td>
                      <td className={tdCls}>{x.work_hours ?? '—'}</td>
                      <td className={tdCls}>{x.late_minutes > 0 ? <span className="font-medium text-amber-700 dark:text-amber-400">{x.late_minutes}</span> : 0}</td>
                      <td className={tdCls}>{x.overtime_minutes}</td><td className={tdCls}>{x.half_day ? 'yes' : 'no'}</td>
                      <td className={tdCls}><button type="button" className={btnSm} onClick={() => openReg(x)}><Wrench className="h-3.5 w-3.5" aria-hidden /> Fix</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <Pager page={page} pageSize={pageSize} total={total} onPage={(p) => load(p)} />
          </div>
        )}
      </Card>
      {reg && (
        <Card title={`Regularize ${reg.emp_code} / ${reg.date}`} icon={Wrench} action={<button type="button" className={btnSm} onClick={() => setReg(null)} aria-label="Close regularization form"><X className="h-4 w-4" aria-hidden /></button>}>
          {rmsg && <p className="mb-3 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">{rmsg}</p>}
          <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={submitReg}>
            <Field label="status (omit = unchanged)">
              <select className={inputCls} value={rform.status} onChange={(e) => setRform({ ...rform, status: e.target.value })}>
                <option value="">(unchanged)</option>
                {['PRESENT', 'WFH', 'ON_DUTY', 'ABSENT', 'LEAVE'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="punch_in"><input className={inputCls} type="datetime-local" value={rform.punch_in} onChange={(e) => setRform({ ...rform, punch_in: e.target.value })} /></Field>
            <Field label="punch_out"><input className={inputCls} type="datetime-local" value={rform.punch_out} onChange={(e) => setRform({ ...rform, punch_out: e.target.value })} /></Field>
            <Field label="reason (min 5 chars)"><input className={inputCls} required minLength={5} maxLength={200} value={rform.reason} onChange={(e) => setRform({ ...rform, reason: e.target.value })} /></Field>
            <Field label="regularized_by"><input className={inputCls} required maxLength={50} value={rform.regularized_by} onChange={(e) => setRform({ ...rform, regularized_by: e.target.value })} /></Field>
            <div className="flex gap-2 sm:col-span-2">
              <button type="submit" className={btnPrimary}>Save correction</button>
              <button type="button" className={btnGhost} onClick={() => setReg(null)}>Close</button>
            </div>
          </form>
        </Card>
      )}
    </div>
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
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Punch in" icon={Clock}>
          <form className="grid grid-cols-1 gap-3" onSubmit={punchIn}>
            <Field label="emp_code"><input className={inputCls} required value={iForm.emp_code} onChange={(e) => setIForm({ ...iForm, emp_code: e.target.value })} /></Field>
            <Field label="at (omit = now)"><input className={inputCls} type="datetime-local" value={iForm.at} onChange={(e) => setIForm({ ...iForm, at: e.target.value })} /></Field>
            <Field label="status">
              <select className={inputCls} value={iForm.status} onChange={(e) => setIForm({ ...iForm, status: e.target.value })}>
                {['PRESENT', 'WFH', 'ON_DUTY'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <div><button type="submit" className={btnPrimary}><Clock className="h-4 w-4" aria-hidden /> Punch in</button></div>
          </form>
        </Card>
        <Card title="Punch out" icon={UserCheck}>
          <form className="grid grid-cols-1 gap-3" onSubmit={punchOut}>
            <Field label="emp_code"><input className={inputCls} required value={oForm.emp_code} onChange={(e) => setOForm({ ...oForm, emp_code: e.target.value })} /></Field>
            <Field label="at (omit = now)"><input className={inputCls} type="datetime-local" value={oForm.at} onChange={(e) => setOForm({ ...oForm, at: e.target.value })} /></Field>
            <div><button type="submit" className={btnPrimary}><UserCheck className="h-4 w-4" aria-hidden /> Punch out</button></div>
          </form>
        </Card>
      </div>
      <StateBanner loading={loading} error={error} />
      {result && !loading && !error && (
        <Card title="Result" icon={RefreshCw}>
          <TableWrap>
            <table className="w-full border-collapse">
              <thead><tr><th className={thCls}>Action</th><th className={thCls}>Date</th><th className={thCls}>Code</th><th className={thCls}>Status</th><th className={thCls}>In</th><th className={thCls}>Out</th><th className={thCls}>Hrs</th><th className={thCls}>Late</th><th className={thCls}>OT</th></tr></thead>
              <tbody><tr className="border-t border-line dark:border-edg">
                <td className={tdCls}>{result.kind}</td><td className={tdCls}>{result.row.date}</td>
                <td className={tdCls}><code className="rounded bg-cream px-1.5 py-0.5 font-mono text-xs dark:bg-elev2">{result.row.emp_code}</code></td>
                <td className={tdCls}><StatusBadge value={result.row.status} /></td>
                <td className={tdCls}>{fmtMs(result.row.punch_in)}</td><td className={tdCls}>{fmtMs(result.row.punch_out)}</td>
                <td className={tdCls}>{result.row.work_hours ?? '—'}</td><td className={tdCls}>{result.row.late_minutes}</td><td className={tdCls}>{result.row.overtime_minutes}</td>
              </tr></tbody>
            </table>
          </TableWrap>
        </Card>
      )}
    </div>
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
    <div className="flex flex-col gap-3">
      <form className="flex flex-wrap items-end gap-3" onSubmit={go}>
        <Field label="emp_code"><input className={inputCls} required value={emp} onChange={(e) => setEmp(e.target.value)} placeholder="EMP0001" /></Field>
        <Field label="month"><input className={inputCls} required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} placeholder="2026-07" /></Field>
        <button type="submit" className={btnPrimary}><BarChart3 className="h-4 w-4" aria-hidden /> Run</button>
      </form>
      <StateBanner loading={loading} error={error} />
      {data && !loading && !error && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {['working_days', 'present_days', 'leave_days', 'late_count', 'total_late_minutes', 'total_overtime_minutes', 'attendance_pct'].map((k) => (
            <div key={k} className="rounded-xl border border-line bg-white p-3 dark:border-edg dark:bg-elev">
              <dt className="text-xs text-fog dark:text-ash">{k}</dt>
              <dd className="text-2xl font-semibold text-ink dark:text-bone">{data[k] ?? '—'}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
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
    <div className="flex flex-col gap-3">
      <form className="flex flex-wrap items-end gap-3" onSubmit={go}>
        <Field label="month"><input className={inputCls} required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
        <Field label="department (optional)"><input className={inputCls} value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <button type="submit" className={btnPrimary}><BarChart3 className="h-4 w-4" aria-hidden /> Run</button>
      </form>
      <StateBanner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <TableWrap>
          <table className="w-full border-collapse">
            <thead><tr><th className={thCls}>Dept</th><th className={thCls}>Headcount</th><th className={thCls}>Present</th><th className={thCls}>Avg hrs</th><th className={thCls}>Late n</th><th className={thCls}>Late min</th><th className={thCls}>Leave</th><th className={thCls}>On duty</th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.department} className="border-t border-line hover:bg-wash dark:border-edg dark:hover:bg-elev2/50">
                  <td className={tdCls}>{x.department}</td><td className={tdCls}>{x.headcount}</td><td className={tdCls}>{x.present_days}</td>
                  <td className={tdCls}>{x.avg_work_hours ?? '—'}</td><td className={tdCls}>{x.late_count}</td>
                  <td className={tdCls}>{x.total_late_minutes}</td><td className={tdCls}>{x.leave_count}</td><td className={tdCls}>{x.on_duty_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </div>
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
    <div className="flex flex-col gap-3">
      <form className="flex flex-wrap items-end gap-3" onSubmit={go}>
        <Field label="month"><input className={inputCls} required pattern="^\d{4}-(0[1-9]|1[0-2])$" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
        <Field label="limit"><input className={inputCls} type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></Field>
        <Field label="department (optional)"><input className={inputCls} value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <button type="submit" className={btnPrimary}><Trophy className="h-4 w-4" aria-hidden /> Run</button>
      </form>
      <StateBanner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <TableWrap>
          <table className="w-full border-collapse">
            <thead><tr><th className={thCls}>Rank</th><th className={thCls}>Code</th><th className={thCls}>Name</th><th className={thCls}>Dept</th><th className={thCls}>Late min</th><th className={thCls}>Late n</th><th className={thCls}><span className="sr-only">Share</span></th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.emp_code} className="border-t border-line hover:bg-wash dark:border-edg dark:hover:bg-elev2/50">
                  <td className={tdCls}>#{x.rank}</td>
                  <td className={tdCls}><code className="rounded bg-cream px-1.5 py-0.5 font-mono text-xs dark:bg-elev2">{x.emp_code}</code></td>
                  <td className={tdCls}>{x.name}</td><td className={tdCls}>{x.department}</td>
                  <td className={tdCls}><span className="font-medium text-amber-700 dark:text-amber-400">{x.total_late_minutes}</span></td>
                  <td className={tdCls}>{x.late_count}</td>
                  <td className={tdCls}><div className="h-2 w-24 rounded bg-wash dark:bg-elev2"><div className="h-2 rounded bg-amber-600/70 dark:bg-amber-500/70" style={{ width: `${(x.total_late_minutes / max) * 100}%` }} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </div>
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
    <div className="flex flex-col gap-3">
      <form className="flex flex-wrap items-end gap-3" onSubmit={go}>
        <Field label="department"><input className={inputCls} required value={dept} onChange={(e) => setDept(e.target.value)} /></Field>
        <Field label="from"><input className={inputCls} required type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="to"><input className={inputCls} required type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <button type="submit" className={btnPrimary}><TrendingUp className="h-4 w-4" aria-hidden /> Run</button>
      </form>
      <StateBanner loading={loading} error={error} empty={items !== null && !loading && !error && items.length === 0} />
      {items?.length > 0 && (
        <TableWrap>
          <table className="w-full border-collapse">
            <thead><tr><th className={thCls}>Date</th><th className={thCls}>Workday</th><th className={thCls}>Headcount</th><th className={thCls}>Present</th><th className={thCls}>Late</th><th className={thCls}>Rate</th><th className={thCls}>7d avg</th><th className={thCls}><span className="sr-only">Share</span></th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.date} className={`border-t border-line hover:bg-wash dark:border-edg dark:hover:bg-elev2/50 ${x.is_working_day ? '' : 'opacity-60'}`}>
                  <td className={tdCls}>{x.date}</td><td className={tdCls}>{x.is_working_day ? 'yes' : 'no'}</td><td className={tdCls}>{x.headcount}</td>
                  <td className={tdCls}>{x.present_count}</td><td className={tdCls}>{x.late_count}</td>
                  <td className={tdCls}>{x.attendance_rate ?? '—'}</td><td className={tdCls}>{x.moving_avg_7d ?? '—'}</td>
                  <td className={tdCls}><div className="h-2 w-24 rounded bg-wash dark:bg-elev2"><div className="h-2 rounded bg-olive-500" style={{ width: `${((x.attendance_rate ?? 0) / max) * 100}%` }} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </div>
  );
}

const ANALYTICS_TABS = [
  { id: 'Monthly', icon: CalendarClock },
  { id: 'Departments', icon: BarChart3 },
  { id: 'Leaderboard', icon: Trophy },
  { id: 'Trend', icon: TrendingUp },
];

function Analytics() {
  const [sub, setSub] = useState('Monthly');
  return (
    <Card title="Analytics" icon={BarChart3}>
      <nav className="mb-4 flex flex-wrap gap-1" aria-label="Analytics sections">
        {ANALYTICS_TABS.map(({ id, icon: Icon }) => (
          <button key={id} type="button" className={tabCls(sub === id)} onClick={() => setSub(id)} aria-current={sub === id ? 'page' : undefined}>
            <Icon className="h-4 w-4" aria-hidden /> {id}
          </button>
        ))}
      </nav>
      {sub === 'Monthly' && <Monthly />}
      {sub === 'Departments' && <Departments />}
      {sub === 'Leaderboard' && <Leaderboard />}
      {sub === 'Trend' && <Trend />}
    </Card>
  );
}

/* ---------------- shell ---------------- */
const NAV = [
  { id: 'Employees', icon: Users, blurb: 'Directory and onboarding' },
  { id: 'Attendance', icon: ClipboardList, blurb: 'Records and corrections' },
  { id: 'Punch', icon: Clock, blurb: 'Punch in and out' },
  { id: 'Analytics', icon: BarChart3, blurb: 'Summaries and trends' },
];

function ThemeToggle() {
  const { mode, cycle } = useTheme();
  const Icon = mode === 'light' ? Sun : mode === 'dark' ? Moon : Monitor;
  const label = `Theme: ${mode}. Activate to switch theme.`;
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={label}
      title={label}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line2 bg-white text-fog hover:bg-cream dark:border-edg dark:bg-elev dark:text-ash dark:hover:bg-elev2"
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}

export default function App() {
  const [tab, setTab] = useState('Employees');
  const [health, setHealth] = useState('');
  useEffect(() => {
    api.health().then(() => setHealth('ok')).catch(() => setHealth('unreachable'));
  }, []);
  const connected = health === 'ok';

  return (
    <div className="min-h-screen bg-cream text-ink dark:bg-coal dark:text-bone">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm">
        Skip to content
      </a>
      <div className="flex min-h-screen flex-col md:flex-row">
        {/* Sidebar / top bar */}
        <aside className="border-b border-line bg-side md:flex md:w-64 md:shrink-0 md:flex-col md:border-b-0 md:border-r dark:border-edg dark:bg-elev">
          <div className="flex items-center gap-2 p-4">
            <div className="flex min-w-0 items-center gap-2.5">
              <img src="/attendx.svg" alt="AttendX logo" width="34" height="34" className="shrink-0" />
              <div className="min-w-0">
                <p className="truncate text-base font-semibold text-ink dark:text-bone">AttendX</p>
                <p className="truncate text-xs text-fog dark:text-ash">Attendance Management</p>
              </div>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:gap-1 md:px-3 md:pb-3" aria-label="Primary">
            {NAV.map(({ id, icon: Icon }) => (
              <button key={id} type="button" className={`${tabCls(tab === id)} w-auto shrink-0 md:w-full`} onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}>
                <Icon className="h-4 w-4" aria-hidden /> {id}
              </button>
            ))}
          </nav>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-side/70 px-4 py-3 sm:px-6 lg:px-8 dark:border-edg dark:bg-elev/60">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold text-ink dark:text-bone">{tab}</h1>
              <p className="truncate text-xs text-fog dark:text-ash">{NAV.find((n) => n.id === tab)?.blurb}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <p
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${connected ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'}`}
                role="status"
              >
                {connected ? <Wifi className="h-3.5 w-3.5" aria-hidden /> : <WifiOff className="h-3.5 w-3.5" aria-hidden />}
                <span className="hidden sm:inline">API {connected ? 'connected' : 'unreachable'}</span>
                <span className="sm:hidden">{connected ? 'on' : 'off'}</span>
              </p>
              <ThemeToggle />
            </div>
          </header>
          <main id="main" className="flex-1 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
            {tab === 'Employees' && <Employees />}
            {tab === 'Attendance' && <Attendance />}
            {tab === 'Punch' && <Punch />}
            {tab === 'Analytics' && <Analytics />}
          </main>
        </div>
      </div>
    </div>
  );
}
