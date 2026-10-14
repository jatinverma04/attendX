import { useCallback, useEffect, useState } from 'react';

const KEY = 'attendx-theme';

function systemDark() {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );
}

function resolve(mode) {
  if (mode === 'dark') return true;
  if (mode === 'light') return false;
  return systemDark();
}

function stored() {
  try {
    return localStorage.getItem(KEY) || 'light';
  } catch {
    return 'light';
  }
}

// 'light' | 'dark' | 'system'. Persists explicit choice, follows the OS
// in system mode, and toggles the `dark` class Tailwind keys off.
export function useTheme() {
  const [mode, setMode] = useState(() => stored());
  const [dark, setDark] = useState(() => resolve(stored()));

  useEffect(() => {
    const apply = (m) => {
      const d = resolve(m);
      setDark(d);
      document.documentElement.classList.toggle('dark', d);
    };
    apply(mode);
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* private mode: keep in-memory choice only */
    }
    if (mode !== 'system' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => apply('system');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [mode]);

  const cycle = useCallback(() => {
    setMode((m) => (m === 'light' ? 'dark' : m === 'dark' ? 'system' : 'light'));
  }, []);

  return { mode, dark, setMode, cycle };
}
