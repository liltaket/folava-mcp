(() => {
  const menuToggle = document.getElementById('site-menu-toggle');
  const navigation = document.getElementById('site-navigation');
  const header = document.querySelector('.header-inner');
  if (menuToggle && navigation && header) {
    const controls = menuToggle.parentElement;
    const compact = window.matchMedia('(max-width: 700px)');
    let menuOpen = false;
    const setMenuOpen = (open, returnFocus = false) => {
      menuOpen = compact.matches && open;
      navigation.hidden = compact.matches && !menuOpen;
      menuToggle.setAttribute('aria-expanded', String(menuOpen));
      menuToggle.setAttribute('aria-label', menuOpen ? 'Close menu' : 'Open menu');
      header.classList.toggle('menu-open', menuOpen);
      if (returnFocus) menuToggle.focus();
    };
    const syncMenu = () => {
      const focused = document.activeElement;
      const focusInNav = navigation.contains(focused);
      // Match keyboard and reading order to the visible layout at each breakpoint.
      if (compact.matches) controls.append(navigation);
      else controls.prepend(navigation);
      menuToggle.hidden = !compact.matches;
      setMenuOpen(false);
      if (compact.matches && focusInNav) menuToggle.focus();
      else if (!compact.matches && focused === menuToggle) navigation.querySelector('a')?.focus();
      else if (!compact.matches && focusInNav) focused.focus();
    };
    syncMenu();
    compact.addEventListener('change', syncMenu);
    menuToggle.addEventListener('click', () => setMenuOpen(!menuOpen));
    navigation.addEventListener('click', event => {
      if (menuOpen && event.target.closest('a')) setMenuOpen(false, true);
    });
    document.addEventListener('click', event => {
      if (menuOpen && !header.contains(event.target)) setMenuOpen(false);
    });
    header.addEventListener('focusout', event => {
      if (menuOpen && event.relatedTarget && !header.contains(event.relatedTarget)) setMenuOpen(false);
    });
    document.getElementById('site-search-open')?.addEventListener('click', () => setMenuOpen(false));
    document.addEventListener('keydown', event => {
      if (!menuOpen) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setMenuOpen(false, true);
      } else if (!event.altKey && !event.shiftKey && !event.isComposing
          && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        setMenuOpen(false, navigation.contains(document.activeElement));
      }
    });
  }
  const themeControl = document.getElementById('theme-toggle');
  if (themeControl && window.folavaTheme) {
    const syncTheme = () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      const label = `Switch to ${next} theme`;
      themeControl.setAttribute('aria-label', label);
      themeControl.title = label;
    };
    syncTheme();
    themeControl.hidden = false;
    themeControl.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      window.folavaTheme.setPreference(next);
    });
    window.addEventListener('themechange', syncTheme);
  }
  const status = document.getElementById('copy-status');
  let clearStatus;
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.hidden = false;
    const action = button.getAttribute('aria-label');
    button.title = action;
    let resetLabel;
    let copying = false;
    let feedback;
    button.addEventListener('click', async () => {
      if (copying) return;
      copying = true;
      clearTimeout(resetLabel);
      feedback?.remove();
      button.title = action;
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
        button.title = 'Copied';
        status.textContent = label + ' copied.';
        resetLabel = setTimeout(() => {
          delete button.dataset.copied;
          button.title = action;
        }, 1800);
      } catch {
        code.closest('details')?.setAttribute('open', '');
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        feedback = document.createElement('p');
        feedback.className = 'copy-feedback';
        feedback.textContent = 'Text selected. Copy it manually.';
        const container = button.closest('.code-block, .setup-command');
        if (container.matches('.setup-command')) container.after(feedback);
        else container.append(feedback);
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
  document.querySelectorAll('[data-responsive-details]').forEach(details => {
    const compact = window.matchMedia(`(max-width: ${details.dataset.responsiveDetails}px)`);
    const sync = () => { details.open = !compact.matches; };
    sync();
    compact.addEventListener('change', sync);
  });
  if (search) {
    document.getElementById('catalog-controls').hidden = false;
    document.getElementById('catalog-fallback').hidden = true;
    const clear = document.getElementById('clear-search');
    const operations = [...document.querySelectorAll('[data-operation]')];
    const count = document.getElementById('operation-count');
    const empty = document.getElementById('empty-search');
    const filter = () => {
      const words = search.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
      let visible = 0;
      operations.forEach(operation => {
        const matches = words.every(word => operation.dataset.search.includes(word));
        operation.hidden = !matches;
        if (matches) visible += 1;
      });
      document.querySelectorAll('[data-operation-group]').forEach(group => {
        const matches = [...group.querySelectorAll('[data-operation]')].filter(item => !item.hidden).length;
        group.hidden = matches === 0;
        const key = group.dataset.operationGroup;
        const link = document.querySelector(`[data-catalog-link="${key}"]`);
        if (link) link.hidden = matches === 0;
        document.querySelectorAll(`[data-group-count="${key}"]`).forEach(count => {
          count.textContent = matches;
        });
      });
      count.textContent = `${visible} of ${operations.length} operations`;
      empty.hidden = visible > 0;
      clear.hidden = search.value.length === 0;
    };
    const clearSearch = () => {
      search.value = '';
      filter();
      search.focus();
    };
    search.addEventListener('input', filter);
    clear.addEventListener('click', clearSearch);
    search.addEventListener('keydown', event => {
      if (event.key === 'Escape' && search.value) {
        event.preventDefault();
        clearSearch();
      }
    });
  }
})();
