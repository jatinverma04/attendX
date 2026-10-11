# DECISIONS.md

1. **Indexes.** `employees(emp_code)` unique rejects duplicate creates at the database, so only one of two simultaneous `POST /employees` inserts wins. `attendance_logs(emp_code, date)` unique does the same for double punch-ins. `attendance_logs(date, emp_code)` serves the list sort (`date` desc, `emp_code` asc) and every month/range `$match`. `employees(department, emp_code)` and `employees(joined_on)` serve department filters and headcount cutoffs. I considered a `status` index and rejected it: status alone is unselective and never queried without a date or employee prefix.

2. **Punch-in race.** Both requests compute the same IST attendance date, then `insert_one`. The unique `(emp_code, date)` index lets exactly one insert succeed; the loser raises `DuplicateKeyError`, mapped to 409. Nothing is read-then-trusted, and punch-out/PATCH use the same pattern with atomic `find_one_and_update` guards (`punch_out: None`, expected field values plus history length).

3. **Ties.** Ranking is `$rank` over `total_late_minutes` descending only, so equal totals share a rank and the next rank skips (1, 1, 3). `limit` filters `rank <= limit` after ranking, so a tie at the cutoff returns more rows than `limit`; final order is total desc, `emp_code` asc.

4. **Headcount.** The summary aggregates from `employees` (`joined_on <= month-end`) with a `$lookup` that preserves employees having no logs, then groups by department, so zero-log people count and later joiners do not.

5. **At 100x data** I would pre-aggregate per-day per-employee facts on write and shard `attendance_logs` by `emp_code`, keeping the same API and indexes.
