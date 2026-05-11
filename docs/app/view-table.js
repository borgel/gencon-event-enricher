// Renders a virtualized list of event-group rows into #results-list.
// Public API: createTableView({ container, rowHeightPx, onRowClick }).
// Call setRows(groups) to update the data; setSelectedKey(key) to highlight.

const OVERSCAN = 8;

export function createTableView({ container, rowHeightPx = 32, onRowClick }) {
  let rows = [];
  let selectedKey = null;
  let userState = { saved: new Set(), purchased: new Set() };

  // DOM: spacer (sets total height) + content layer (positions absolute rows).
  const spacer = document.createElement('div');
  spacer.style.position = 'relative';
  spacer.style.height = '0px';
  container.innerHTML = '';
  container.appendChild(spacer);
  container.style.position = 'relative';

  const visible = new Map(); // index -> DOM row

  function render() {
    const scrollTop = container.scrollTop;
    const viewport = container.clientHeight;
    const startIdx = Math.max(0, Math.floor(scrollTop / rowHeightPx) - OVERSCAN);
    const endIdx = Math.min(rows.length, Math.ceil((scrollTop + viewport) / rowHeightPx) + OVERSCAN);

    // Remove rows outside [startIdx, endIdx).
    for (const [idx, el] of [...visible]) {
      if (idx < startIdx || idx >= endIdx) {
        el.remove();
        visible.delete(idx);
      }
    }
    // Add rows inside the window.
    for (let i = startIdx; i < endIdx; i++) {
      if (visible.has(i)) continue;
      const el = makeRow(rows[i], userState);
      el.style.position = 'absolute';
      el.style.top = (i * rowHeightPx) + 'px';
      el.style.left = '0'; el.style.right = '0';
      if (rows[i].key === selectedKey) el.classList.add('selected');
      el.addEventListener('click', () => onRowClick && onRowClick(rows[i].key));
      spacer.appendChild(el);
      visible.set(i, el);
    }
  }

  container.addEventListener('scroll', render, { passive: true });
  window.addEventListener('resize', render);

  return {
    setRows(newRows, newUserState) {
      // Heuristic: if the row count and edges match, we treat this as an
      // in-place refresh (e.g. user toggled saved/purchased on an event in
      // the detail panel) and preserve scroll. Otherwise reset to top.
      const sameShape =
        rows.length === newRows.length &&
        rows[0]?.key === newRows[0]?.key &&
        rows[rows.length - 1]?.key === newRows[newRows.length - 1]?.key;
      rows = newRows;
      if (newUserState) userState = newUserState;
      spacer.style.height = (newRows.length * rowHeightPx) + 'px';
      // Hard reset visible map (group identities may differ even if indices line up).
      for (const el of visible.values()) el.remove();
      visible.clear();
      if (!sameShape) container.scrollTop = 0;
      render();
    },
    setSelectedKey(key) {
      selectedKey = key;
      for (const [idx, el] of visible) {
        el.classList.toggle('selected', rows[idx]?.key === key);
      }
    },
    scrollToKey(key) {
      // Linear search is fine — dataset is at most ~50k rows; this runs once
      // per Lucky-button click, not per scroll.
      const idx = rows.findIndex((r) => r.key === key);
      if (idx < 0) return false;
      const desiredTop = idx * rowHeightPx - container.clientHeight / 2;
      container.scrollTop = Math.max(0, desiredTop);
      render();
      return true;
    },
  };
}

function makeRow(g, userState) {
  const row = document.createElement('div');
  row.className = 'row';
  if (userState?.conflicts && userState.conflicts.has(g.key)) {
    row.classList.add('conflict');
  }
  row.innerHTML = `
    <span class="marks">${formatMarks(g, userState)}</span>
    <span class="when">${formatWhen(g)}</span>
    <span class="title">${escape(g.title)} <span class="meta">${formatMeta(g)}</span></span>
    <span class="meta">${escape(g.event_type)}</span>
    <span class="tix ${ticketsClass(g)}">${formatTix(g)}</span>
    <span class="bgg ${g.bgg ? '' : 'none'}">${formatBgg(g)}</span>
  `;
  return row;
}

function formatMarks(g, userState) {
  const saved = userState?.saved && g.sessions?.some(s => userState.saved.has(s.gencon_id));
  const purchased = userState?.purchased && g.sessions?.some(s => userState.purchased.has(s.gencon_id));
  const conflict = userState?.conflicts && userState.conflicts.has(g.key);
  return `${conflict ? '⚠️' : ''}${purchased ? '🎟️' : ''}${saved ? '★' : ''}`;
}

export function formatWhen(g) {
  const sessions = g.sessions || [];
  if (!sessions.length) return '';
  if (sessions.length === 1) {
    return formatSingleSession(sessions[0]);
  }
  // Multi-session: derive first and last day codes from sorted starts.
  const sortedStarts = sessions.map(s => s.start).sort();
  const firstDay = dayCodeFromIso(sortedStarts[0]);
  const lastDay = dayCodeFromIso(sortedStarts[sortedStarts.length - 1]);
  if (firstDay === lastDay) {
    return `${sessions.length}× ${firstDay}`;
  }
  return `${sessions.length}× ${firstDay}–${lastDay}`;
}

function formatSingleSession(s) {
  const d = new Date(s.start);
  const day = dayCodeFromIso(s.start);
  const h = d.getHours();
  const m = d.getMinutes();
  const ampm = h < 12 ? 'a' : 'p';
  const h12 = ((h + 11) % 12) + 1;
  return m === 0
    ? `${day} ${h12}${ampm}`
    : `${day} ${h12}:${String(m).padStart(2, '0')}${ampm}`;
}

function dayCodeFromIso(iso) {
  const d = new Date(iso);
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
}

function formatMeta(g) {
  const dur = g.duration_minutes ? `${(g.duration_minutes / 60).toFixed(g.duration_minutes % 60 ? 1 : 0)}h` : '';
  const sessions = g.sessions.length > 1 ? ` · ${g.sessions.length} sessions` : '';
  return `· ${dur}${sessions}`;
}

function ticketsClass(g) {
  const total = g.sessions.reduce((sum, s) => sum + (s.tickets_available ?? 0), 0);
  return total > 0 ? 'have' : 'gone';
}
function formatTix(g) {
  const total = g.sessions.reduce((sum, s) => sum + (s.tickets_available ?? 0), 0);
  return total > 0 ? String(total) : '0';
}
function formatBgg(g) {
  if (!g.bgg || g.bgg.bayesaverage == null) return '—';
  return `★ ${g.bgg.bayesaverage.toFixed(2)}`;
}

function escape(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
