# AttendX frontend

React + Vite dashboard for the AttendX API.

```bash
npm install
npm run dev        # http://localhost:5173 (API expected on :8000)
npm run build      # production bundle in dist/
npm run lint
npm run test:e2e   # Playwright suite; needs the API running on :8000
```

`VITE_API_BASE` overrides the API base URL (defaults to `http://127.0.0.1:8000`).

Theme: Light is the default for first-time visitors; the header button cycles
Light → Dark → System and the choice is persisted in `localStorage`
(`attendx-theme`). Tokens live in `src/index.css`, the hook in `src/theme.js`.
