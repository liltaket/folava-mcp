// Runs before the stylesheet so the first paint uses the visitor's theme.
(() => {
  const key = 'folava-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const valid = value => ['system', 'light', 'dark'].includes(value);
  let preference = 'system';
  try {
    const saved = window.localStorage.getItem(key);
    if (valid(saved)) preference = saved;
  } catch { /* The system preference still works when storage is blocked. */ }

  const apply = () => {
    const theme = preference === 'system'
      ? (system.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      'content', theme === 'dark' ? '#18181b' : '#ffffff',
    );
    window.dispatchEvent(new Event('themechange'));
  };
  window.folavaTheme = {
    getPreference: () => preference,
    setPreference: value => {
      if (!valid(value)) return;
      preference = value;
      try { window.localStorage.setItem(key, value); } catch { /* Session-only fallback. */ }
      apply();
    },
  };
  system.addEventListener('change', () => {
    if (preference === 'system') apply();
  });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : 'system';
    apply();
  });
  apply();
})();
