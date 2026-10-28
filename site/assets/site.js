(() => {
  const themeControl = document.getElementById('theme-choice');
  if (themeControl && window.folavaTheme) {
    const syncTheme = () => { themeControl.value = window.folavaTheme.getPreference(); };
    syncTheme();
    themeControl.closest('.theme-control').hidden = false;
    themeControl.addEventListener('change', () => {
      window.folavaTheme.setPreference(themeControl.value);
    });
    window.addEventListener('themechange', syncTheme);
  }
  const status = document.getElementById('copy-status');
  let clearStatus;
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.hidden = false;
    let resetLabel;
    let copying = false;
    button.addEventListener('click', async () => {
      if (copying) return;
      copying = true;
      button.setAttribute('aria-busy', 'true');
      delete button.dataset.copied;
      const code = button.dataset.copyTarget
        ? document.getElementById(button.dataset.copyTarget)
        : button.closest('.code-block').querySelector('code');
      const label = button.dataset.copyLabel || 'Command';
      try {
        if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
        await navigator.clipboard.writeText(code.textContent);
        button.dataset.copied = 'true';
        status.textContent = label + ' copied.';
        clearTimeout(resetLabel);
        resetLabel = setTimeout(() => { delete button.dataset.copied; }, 1800);
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'Copy is unavailable here. The ' + label.toLowerCase()
          + ' is selected; copy it manually.';
      } finally {
        copying = false;
        button.removeAttribute('aria-busy');
      }
      clearTimeout(clearStatus);
      clearStatus = setTimeout(() => { status.textContent = ''; }, 5000);
    });
  });
  const tabs = [...document.querySelectorAll('[data-example]')];
  const selectTab = tab => {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    });
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        selectTab(tabs[next]);
        tabs[next].focus();
      }
    });
  });
  const search = document.getElementById('operation-search');
  if (search) {
    const operations = [...document.querySelectorAll('[data-operation]')];
    const count = document.getElementById('operation-count');
    const empty = document.getElementById('empty-search');
    search.addEventListener('input', () => {
      const words = search.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
      let visible = 0;
      operations.forEach(operation => {
        const matches = words.every(word => operation.dataset.search.includes(word));
        operation.hidden = !matches;
        if (matches) visible += 1;
      });
      count.textContent = `${visible} of ${operations.length} operations`;
      empty.hidden = visible > 0;
    });
  }
})();
