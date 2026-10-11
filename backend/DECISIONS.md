# DECISIONS.md

1. **Indexes.** Unique `employees(emp_code)` and `attendance_logs(emp_code, date)` make exactly one of two simultaneous creates/punch-ins win. `attendance_logs(date, emp_code)` serves the list sort and every month/range `$match`; `employees(department, emp_code)` and `employees(joined_on)` serve department filters and headcount cutoffs. A `status` index was rejected: unselective and never queried alone.

2. **Punch-in race.** Both requests compute the same IST date, then `insert_one`. One insert wins; the loser raises `DuplicateKeyError`, mapped to 409. Punch-out/PATCH use atomic `find_one_and_update` guards (`punch_out: None`; expected values plus history length).

3. **Ties.** `$rank` runs over `total_late_minutes` only, so equal totals share a rank and the next skips (1, 1, 3). `limit` filters `rank <= limit` after ranking, so a cutoff tie returns extra rows; order is total desc, `emp_code` asc.

4. **Headcount.** The summary aggregates from `employees` (`joined_on <= month-end`) with a `$lookup` preserving log-less employees, then groups by department — zero-log people count, later joiners do not.

5. **At 100x data** I would pre-aggregate per-day facts on write and shard `attendance_logs` by `emp_code`, and serve analytics from read replicas,
keeping the same API and index shapes.
