(() => {
  // Catalog links work on arrival and with browser history, even without opening search.
  const openOperation = hash => {
    let id;
    try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
    if (!id.startsWith('op-')) return;
    const operation = document.getElementById(id);
    if (!operation?.matches('details[data-operation]')) return;
    const localSearch = document.getElementById('operation-search');
    if (localSearch?.value) {
      localSearch.value = '';
      localSearch.dispatchEvent(new Event('input', { bubbles: true }));
    }
    operation.hidden = false;
    operation.open = true;
    requestAnimationFrame(() => operation.scrollIntoView({ block: 'start' }));
  };
  openOperation(location.hash);
  window.addEventListener('hashchange', () => openOperation(location.hash));

  const trigger = document.getElementById('site-search-open');
  const dialog = document.getElementById('site-search');
  const input = document.getElementById('site-search-input');
  const results = document.getElementById('site-search-results');
  const state = document.getElementById('site-search-state');
  const closeButton = document.getElementById('site-search-close');
  const retry = document.getElementById('site-search-retry');
  if (!trigger || !dialog || !input || !results || !state || !closeButton || !retry
      || typeof dialog.showModal !== 'function' || !window.fetch || !window.AbortController) return;

  let base;
  let indexURL;
  try {
    base = new URL(trigger.dataset.searchBase, location.href);
    indexURL = new URL(trigger.dataset.searchIndex, location.href);
    if (!['http:', 'https:'].includes(base.protocol) || base.origin !== location.origin
        || !base.pathname.endsWith('/') || base.search || base.hash
        || indexURL.origin !== base.origin || !indexURL.pathname.startsWith(base.pathname)
        || indexURL.username || indexURL.password || base.username || base.password) return;
  } catch { return; }

  const LIMIT = 8;
  const fold = value => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const wordsOf = value => fold(value).replace(/[^a-z0-9\u0080-\uffff]+/g, ' ').trim();
  let entries;
  let loading;
  let active = -1;
  let links = [];
  let session = 0;
  let opener;

  const validateIndex = data => {
    if (!data || data.version !== 1 || !Array.isArray(data.entries)
        || data.entries.length > 20000) throw new Error('Invalid search index');
    return data.entries.map((entry, order) => {
      if (!entry || !['guide', 'api'].includes(entry.kind)
          || !['title', 'context', 'url', 'text'].every(key => typeof entry[key] === 'string')
          || !entry.title.trim() || entry.title.length > 1000 || entry.context.length > 2000
          || (entry.summary !== undefined && (typeof entry.summary !== 'string' || entry.summary.length > 2000))
          || entry.text.length > 200000 || entry.url.length > 4000
          || !entry.url || /^[\/\\]/.test(entry.url)
          || /[\s\u0000-\u001f\u007f\\]/.test(entry.url)
          || /^[a-z][a-z0-9+.-]*:/i.test(entry.url)) throw new Error('Invalid search entry');
      const url = new URL(entry.url, base);
      if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)
          || /%(?:2f|5c)/i.test(url.pathname) || url.username || url.password)
        throw new Error('Invalid search target');
      let operationID = '';
      if (entry.kind === 'api') {
        try { operationID = decodeURIComponent(url.hash.slice(1)).replace(/^op-/, ''); }
        catch { throw new Error('Invalid operation target'); }
      }
      const title = wordsOf(entry.title);
      const context = wordsOf(entry.context);
      const text = wordsOf(entry.text);
      const id = wordsOf(operationID);
      return { ...entry, href: url.href, titleKey: fold(entry.title), titleWords: title,
        contextWords: context, textWords: text, idKey: fold(operationID), idWords: id,
        allWords: `${title} ${context} ${text} ${id}`, order };
    });
  };

  const getIndex = () => {
    if (entries) return Promise.resolve(entries);
    if (!loading) {
      loading = (async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
          const response = await fetch(indexURL.href, {
            signal: controller.signal, credentials: 'omit', mode: 'same-origin', redirect: 'error',
          });
          if (!response.ok) throw new Error('Search index unavailable');
          const source = await response.text();
          if (source.length > 8000000) throw new Error('Search index too large');
          entries = validateIndex(JSON.parse(source));
          return entries;
        } finally { clearTimeout(timeout); }
      })().finally(() => { loading = undefined; });
    }
    return loading;
  };

  const setActive = (index, scroll = false) => {
    active = index;
    links.forEach((link, position) => link.setAttribute('aria-selected', String(position === index)));
    if (links[index]) {
      input.setAttribute('aria-activedescendant', links[index].id);
      if (scroll) links[index].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  };

  const clearResults = () => {
    results.replaceChildren();
    links = [];
    setActive(-1);
  };

  const rank = (entry, query, words, phrase) => {
    if (!words.every(word => entry.allWords.includes(word))) return 0;
    let score = entry.idKey === query ? 1400 : 0;
    if (entry.titleKey === query) score += 1200;
    if (entry.titleWords === phrase) score += 600;
    if (entry.titleWords.startsWith(phrase)) score += 180;
    if (entry.titleWords.includes(phrase)) score += 100;
    if (entry.idWords.includes(phrase)) score += 100;
    words.forEach(word => {
      if (entry.titleWords.includes(word)) score += 40;
      if (entry.idWords.includes(word)) score += 35;
      if (entry.contextWords.includes(word)) score += 15;
      if (entry.textWords.includes(word)) score += 1;
    });
    return score || 1;
  };

  const snippet = (entry, words) => {
    const source = (entry.summary ?? entry.text).replace(/\s+/g, ' ').trim();
    const text = source.startsWith(entry.title) ? source.slice(entry.title.length).trim() : source;
    if (!text) return '';
    const lower = fold(text);
    const positions = words.map(word => lower.indexOf(word)).filter(index => index >= 0);
    let start = positions.length ? Math.max(0, Math.min(...positions) - 42) : 0;
    if (start) {
      const boundary = text.indexOf(' ', start);
      if (boundary !== -1 && boundary < start + 20) start = boundary + 1;
    }
    const excerpt = text.slice(start, start + 110).trim();
    return `${start ? '…' : ''}${excerpt}${start + excerpt.length < text.length ? '…' : ''}`;
  };

  const close = () => {
    session += 1;
    if (dialog.open) dialog.close();
  };

  const render = () => {
    if (!entries || !dialog.open) return;
    clearResults();
    retry.hidden = true;
    const query = fold(input.value);
    const phrase = wordsOf(query);
    const words = phrase.split(' ').filter(Boolean);
    let matches;
    if (query) {
      matches = words.length ? entries.map(entry => ({ entry, score: rank(entry, query, words, phrase) }))
        .filter(match => match.score > 0)
        .sort((a, b) => b.score - a.score || a.entry.order - b.entry.order)
        .map(match => match.entry) : [];
    } else {
      const guides = entries.filter(entry => entry.kind === 'guide');
      const pages = guides.filter(entry => !new URL(entry.href).hash);
      matches = [...(pages.length ? pages : guides).slice(0, 4),
        ...entries.filter(entry => entry.kind === 'api').slice(0, 1)];
    }
    matches.slice(0, LIMIT).forEach((entry, index) => {
      const item = document.createElement('li');
      item.setAttribute('role', 'presentation');
      const link = document.createElement('a');
      link.className = 'search-result';
      link.id = `site-search-result-${index}`;
      link.href = entry.href;
      link.tabIndex = -1;
      link.setAttribute('role', 'option');
      const title = document.createElement('span');
      title.className = 'search-result-title';
      title.textContent = entry.title;
      const meta = document.createElement('span');
      meta.className = 'search-result-meta';
      const kind = document.createElement('span');
      kind.className = 'search-result-kind';
      kind.textContent = entry.kind === 'api' ? 'API' : 'Guide';
      meta.append(kind);
      if (entry.context) {
        const context = document.createElement('span');
        context.className = 'search-result-context';
        context.textContent = entry.context;
        meta.append(context);
      }
      link.append(meta, title);
      const excerpt = query ? snippet(entry, words) : '';
      if (excerpt) {
        const detail = document.createElement('span');
        detail.className = 'search-result-snippet';
        detail.textContent = excerpt;
        link.append(detail);
      }
      link.addEventListener('pointermove', () => setActive(index));
      link.addEventListener('pointerdown', event => {
        if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey)
          event.preventDefault();
      });
      link.addEventListener('click', event => {
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const url = new URL(entry.href);
        close();
        if (url.pathname === location.pathname && url.search === location.search)
          openOperation(url.hash);
      });
      item.append(link);
      results.append(item);
      links.push(link);
    });
    setActive(links.length ? 0 : -1);
    state.textContent = !query ? (links.length ? 'Suggestions' : 'No search entries are available.')
      : !matches.length ? 'No results. Try a different word or an operation ID.'
        : matches.length > LIMIT ? `Showing ${LIMIT} of ${matches.length} results.`
          : `${matches.length} ${matches.length === 1 ? 'result' : 'results'}.`;
  };

  const load = async () => {
    const current = ++session;
    clearResults();
    retry.hidden = true;
    input.setAttribute('aria-busy', 'true');
    state.textContent = 'Loading search…';
    try {
      await getIndex();
      if (current === session && dialog.open) render();
    } catch {
      if (current !== session || !dialog.open) return;
      state.textContent = 'Search could not load. Please try again, or browse the Guide and API catalog.';
      retry.hidden = false;
    } finally {
      if (current === session && dialog.open) input.removeAttribute('aria-busy');
    }
  };

  const open = () => {
    if (dialog.open) return;
    session += 1;
    opener = document.activeElement;
    dialog.showModal();
    input.setAttribute('aria-expanded', 'true');
    input.removeAttribute('aria-busy');
    input.focus({ preventScroll: true });
    input.select();
    if (entries) render();
    else load();
  };

  trigger.querySelectorAll('[data-search-shortcut]').forEach(shortcut => {
    shortcut.textContent = /Mac|iPhone|iPad|iPod/.test(navigator.platform) ? '⌘ K' : 'Ctrl K';
  });
  trigger.hidden = false;
  trigger.addEventListener('click', open);
  closeButton.addEventListener('click', close);
  retry.addEventListener('click', load);
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey) return;
    const controls = [...dialog.querySelectorAll('button, input, a[href], [tabindex]')]
      .filter(element => element.tabIndex >= 0 && !element.disabled && element.getClientRects().length);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if ((event.shiftKey && document.activeElement === first)
        || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  });
  input.addEventListener('input', render);
  input.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229 || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && links.length) {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setActive((active + direction + links.length) % links.length, true);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      links[active]?.click();
    }
  });
  dialog.addEventListener('close', () => {
    // A queued close event can arrive after a shortcut has reopened the dialog.
    if (dialog.open) return;
    session += 1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-busy');
    input.removeAttribute('aria-activedescendant');
    if (opener?.isConnected) opener.focus({ preventScroll: true });
  });
  const outside = event => {
    const bounds = dialog.getBoundingClientRect();
    return event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right
      || event.clientY < bounds.top || event.clientY > bounds.bottom);
  };
  let backdropPress = false;
  dialog.addEventListener('pointerdown', event => { backdropPress = outside(event); });
  dialog.addEventListener('pointercancel', () => { backdropPress = false; });
  dialog.addEventListener('click', event => {
    if (backdropPress && outside(event)) close();
    backdropPress = false;
  });
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.isComposing || event.keyCode === 229 || event.altKey
        || event.shiftKey || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return;
    event.preventDefault();
    if (dialog.open) close();
    else open();
  });
})();
