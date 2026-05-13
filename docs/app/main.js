import { loadData } from './data.js';
import { defaultState, buildPredicate, stateToHash, hashToState } from './filters.js';
import { buildIndex, searchKeys } from './search.js';
import { getSaved, getPurchased, replaceSaved, replacePurchased } from './saved.js';
import { exportSchedule, parseScheduleCSV, triggerDownload } from './schedule.js';
import { createTableView } from './view-table.js';
import { createDetailView } from './view-detail.js';
import { createTimelineView } from './view-timeline.js';
import { KEY_OPTIONS, LABELS, compareGroups } from './sort.js';
import { groupOverlapMap } from './conflict.js';
import { listCollections, createCollection, replaceCollection, findByName, getMyName, setMyName, getCollection } from './collections.js';

const $ = (sel) => document.querySelector(sel);
const groupsByKey = new Map();
let lastVisibleGroups = [];

function renderHeaderMeta(meta) {
  const m = meta || {};
  $('#header-meta').textContent =
    `${m.stats?.groups ?? '?'} groups · ${m.stats?.sessions ?? '?'} sessions ` +
    `· generated ${m.generated_at ?? '?'}`;
}

function renderFilterRail(state, onChange) {
  const html = `
    <div class="group">
      <div class="label">Search</div>
      <input type="text" id="f-search" value="${escapeAttr(state.search)}" placeholder="title, description, game system">
    </div>
    <div class="group">
      <div class="label">Day</div>
      <div id="f-days">
        ${['thu','fri','sat','sun'].map(d => `<span class="chip ${state.days.has(d)?'active':''}" data-day="${d}">${d.toUpperCase()}</span>`).join('')}
      </div>
    </div>
    <div class="group">
      <div class="label">Hour range (${state.hourMin}:00 – ${state.hourMax}:00)</div>
      <input type="range" id="f-hmin" min="0" max="24" value="${state.hourMin}">
      <input type="range" id="f-hmax" min="0" max="24" value="${state.hourMax}">
    </div>
    <div class="group">
      <div class="label">Type (multi)</div>
      <div class="multiselect-controls">
        <button id="f-types-all" type="button">Select all</button>
        <button id="f-types-none" type="button">Clear all</button>
      </div>
      <div id="f-types"></div>
    </div>
    <div class="group">
      <div class="label">Duration (${formatDurH(state.durMinH)} – ${formatDurH(state.durMaxH, true)})</div>
      <input type="range" id="f-durmin" min="0" max="12" step="0.5" value="${state.durMinH}">
      <input type="range" id="f-durmax" min="0" max="12" step="0.5" value="${state.durMaxH}">
    </div>
    <div class="group">
      <div class="label">Party size</div>
      <input type="number" id="f-party" min="0" max="20" value="${state.party}">
    </div>
    <div class="group">
      <div class="label">Cost</div>
      <select id="f-cost">
        <option value=""${state.costBand===''?' selected':''}>any</option>
        <option value="0"${state.costBand==='0'?' selected':''}>free</option>
        <option value="0-10"${state.costBand==='0-10'?' selected':''}>$0–$10</option>
        <option value="10+"${state.costBand==='10+'?' selected':''}>$10+</option>
      </select>
    </div>
    <div class="group">
      <div class="label">Age</div>
      <input type="text" id="f-age" value="${escapeAttr(state.age)}" placeholder="e.g. Teen (13+)">
    </div>
    <div class="group">
      <div class="label">Experience</div>
      <input type="text" id="f-exp" value="${escapeAttr(state.experience)}" placeholder="e.g. None">
    </div>
    <div class="group">
      <div class="label">Location</div>
      <div id="f-locations"></div>
    </div>
    <div class="group">
      <div class="label">BGG geek-rating ≥ ${state.bggMin || 0}</div>
      <input type="range" id="f-bgg" min="0" max="9" step="0.1" value="${state.bggMin}">
    </div>
    <div class="group">
      <div class="label">BGG match</div>
      <div id="f-bggmatch">
        ${['either','yes','no'].map(v =>
          `<span class="chip ${state.bggMatch===v?'active':''}" data-bgg="${v}">${
            v==='either'?'Any': v==='yes'?'Has match':'No match'
          }</span>`
        ).join('')}
      </div>
    </div>
    <div class="group">
      <label><input type="checkbox" id="f-tix" ${state.ticketsOnly?'checked':''}> Tickets available</label><br>
      <label><input type="checkbox" id="f-tournament" ${state.tournament==='yes'?'checked':''}> Tournament only</label>
    </div>
    <section id="friends-lists" class="rail-section hidden"></section>
    <div class="group">
      <button id="f-clear" type="button">Clear filters</button>
    </div>
    <div class="group">
      <div class="label">Schedule</div>
      <button id="f-export" type="button">Export schedule</button>
      <label class="file-button" for="f-import">Import schedule</label>
      <input type="file" id="f-import" accept=".csv,text/csv" hidden>
    </div>
  `;
  $('#filter-rail').innerHTML = html;

  const wire = (id, evt, fn) => $(id).addEventListener(evt, (e) => { fn(e); onChange(); });
  wire('#f-search', 'input', (e) => state.search = e.target.value);
  wire('#f-hmin', 'input', (e) => state.hourMin = +e.target.value);
  wire('#f-hmax', 'input', (e) => state.hourMax = +e.target.value);
  const updateDurLabel = () => {
    const lbl = $('#f-durmin').previousElementSibling;
    lbl.textContent = `Duration (${formatDurH(state.durMinH)} – ${formatDurH(state.durMaxH, true)})`;
  };
  wire('#f-durmin', 'input', (e) => { state.durMinH = +e.target.value; updateDurLabel(); });
  wire('#f-durmax', 'input', (e) => { state.durMaxH = +e.target.value; updateDurLabel(); });
  wire('#f-party', 'input', (e) => state.party = +e.target.value || 0);
  wire('#f-cost', 'change', (e) => state.costBand = e.target.value);
  wire('#f-age', 'input', (e) => state.age = e.target.value);
  wire('#f-exp', 'input', (e) => state.experience = e.target.value);
  wire('#f-bgg', 'input', (e) => state.bggMin = +e.target.value);
  wire('#f-tix', 'change', (e) => state.ticketsOnly = e.target.checked);
  wire('#f-tournament', 'change', (e) => state.tournament = e.target.checked ? 'yes' : 'either');

  $('#f-bggmatch').addEventListener('click', (e) => {
    const v = e.target.dataset.bgg; if (!v) return;
    state.bggMatch = v;
    for (const chip of document.querySelectorAll('#f-bggmatch .chip')) {
      chip.classList.toggle('active', chip.dataset.bgg === v);
    }
    onChange();
  });
  $('#f-days').addEventListener('click', (e) => {
    const d = e.target.dataset.day; if (!d) return;
    if (state.days.has(d)) state.days.delete(d); else state.days.add(d);
    e.target.classList.toggle('active');
    onChange();
  });
}

function renderResultsToolbar(state, onChange) {
  const html = `
    <div class="toolbar-left">
      <label for="s-key">Sort:</label>
      <select id="s-key">
        ${KEY_OPTIONS.map(([v, l]) =>
          `<option value="${v}"${state.sortKey === v ? ' selected' : ''}>${l}</option>`
        ).join('')}
      </select>
      <button id="s-dir" type="button">${LABELS[state.sortKey][state.sortDir]}</button>
    </div>
    <div class="toolbar-right">
      <button id="s-timeline" type="button" class="${state.viewMode === 'timeline' ? 'active' : ''}">🗓️ Timeline</button>
      <button id="s-saved" type="button" class="${state.mineActive ? 'active' : ''}">★ Saved (0)</button>
      <button id="s-lucky" type="button" disabled>🎲 I'm Feeling Lucky</button>
    </div>
  `;
  document.querySelector('#results-toolbar').innerHTML = html;

  document.querySelector('#s-key').addEventListener('change', (e) => {
    state.sortKey = e.target.value;
    // Reset direction to that key's natural default (start=asc, type=asc, bgg=desc).
    state.sortDir = e.target.value === 'bgg' ? 'desc' : 'asc';
    document.querySelector('#s-dir').textContent = LABELS[state.sortKey][state.sortDir];
    onChange();
  });
  document.querySelector('#s-dir').addEventListener('click', () => {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    document.querySelector('#s-dir').textContent = LABELS[state.sortKey][state.sortDir];
    onChange();
  });
  document.querySelector('#s-saved').addEventListener('click', () => {
    state.mineActive = !state.mineActive;
    onChange();
  });
  document.querySelector('#s-timeline').addEventListener('click', () => {
    state.viewMode = state.viewMode === 'timeline' ? 'list' : 'timeline';
    onChange();
  });
}

function populateMultiselect(id, values, set, onChange, labels = {}) {
  const target = document.getElementById(id);
  target.innerHTML = values.map(v => {
    const text = labels[v] || v;
    return `<span class="chip ${set.has(v)?'active':''}" data-val="${escapeAttr(v)}">${escapeAttr(text)}</span>`;
  }).join('');
  target.addEventListener('click', (e) => {
    const v = e.target.dataset.val; if (!v) return;
    if (set.has(v)) set.delete(v); else set.add(v);
    e.target.classList.toggle('active');
    onChange();
  });
}

async function main() {
  const blob = await loadData();
  renderHeaderMeta(blob.meta);

  // Drawer toggle — only meaningful at phone width but the listeners are
  // safe to attach unconditionally (the hamburger is display:none on desktop).
  function setLockScroll() {
    const open = document.body.classList.contains('drawer-open')
              || !document.querySelector('#detail-panel').classList.contains('hidden');
    document.body.classList.toggle('lock-scroll', open);
  }
  $('#hamburger').addEventListener('click', () => {
    document.body.classList.toggle('drawer-open');
    setLockScroll();
  });
  $('#drawer-backdrop').addEventListener('click', () => {
    document.body.classList.remove('drawer-open');
    setLockScroll();
  });

  for (const g of blob.groups) groupsByKey.set(g.key, g);

  let state = hashToState(window.location.hash);
  const index = buildIndex(blob.groups);
  let openGroup = null;
  let latestOverlap = { conflictedGroups: new Set(), perSession: new Map() };

  // Build a "Full Label (CODE)" map from the dataset. event_type_label in
  // GenCon data is formatted "CODE - Full Label" — strip the "CODE - " prefix.
  const typeLabels = {};
  for (const g of blob.groups) {
    if (typeLabels[g.event_type]) continue;
    const raw = g.event_type_label || g.event_type;
    const m = raw.match(/^[A-Z]+\s*-\s*(.+)$/);
    const human = (m ? m[1] : raw).trim();
    typeLabels[g.event_type] = `${human} (${g.event_type})`;
  }
  const uniqueTypes = [...new Set(blob.groups.map(g => g.event_type))].sort();
  const uniqueLocations =
    [...new Set(blob.groups.map(g => g.sessions[0]?.location).filter(Boolean))].sort();

  const tableView = createTableView({
    container: $('#results-list'),
    onRowClick: (key) => {
      const g = groupsByKey.get(key);
      detailView.show(g, latestOverlap.perSession, { allCollections: listCollections() });
    },
  });
  const detailView = createDetailView({
    panel: $('#detail-panel'),
    onChange: () => applyFilters(),
    onShow: (g) => { openGroup = g; setLockScroll(); },
    onClose: () => { openGroup = null; setLockScroll(); },
  });
  const timelineView = createTimelineView({
    container: $('#results-timeline'),
    onEventClick: (g) => detailView.show(g, latestOverlap.perSession, { allCollections: listCollections() }),
  });

  function attachLuckyHandler() {
    document.querySelector('#s-lucky').addEventListener('click', () => {
      if (!lastVisibleGroups.length) return;
      const g = lastVisibleGroups[Math.floor(Math.random() * lastVisibleGroups.length)];
      detailView.show(g, latestOverlap.perSession, { allCollections: listCollections() });
      tableView.scrollToKey(g.key);
      tableView.setSelectedKey(g.key);
    });
  }

  function renderFriendsLists() {
    const container = document.querySelector('#friends-lists');
    if (!container) return;
    const collections = listCollections();
    if (collections.length === 0) {
      container.classList.add('hidden');
      container.innerHTML = '';
      return;
    }
    container.classList.remove('hidden');
    const rowsHtml = collections.map(c => {
      const checked = state.activeListIds.has(c.id) ? 'checked' : '';
      const total = c.saved.length + c.purchased.length;
      return `
        <label class="friend-list-row" data-id="${c.id}">
          <input type="checkbox" ${checked} data-id="${c.id}">
          <span class="swatch" style="background:${c.color}"></span>
          <span class="name">${escapeHtml(c.name)}</span>
          <span class="count">${total}</span>
        </label>
      `;
    }).join('');
    container.innerHTML = `
      <h4>Friend's Lists</h4>
      ${rowsHtml}
      <a class="manage-link" href="#" id="manage-collections-link">Manage…</a>
    `;
    container.querySelectorAll('input[type=checkbox]').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const id = e.target.dataset.id;
        if (e.target.checked) state.activeListIds.add(id);
        else state.activeListIds.delete(id);
        applyFilters();
      });
    });
    const manageLink = container.querySelector('#manage-collections-link');
    if (manageLink) {
      manageLink.addEventListener('click', (e) => {
        e.preventDefault();
        console.log('manage clicked');
      });
    }
  }

  function attachScheduleHandlers() {
    document.querySelector('#f-export').addEventListener('click', () => {
      openExportModal();
    });
    document.querySelector('#f-import').addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const text = await file.text();
      const result = parseScheduleCSV(text, blob.groups);
      openImportModal(result, text);
      // Reset so the same file can be re-selected later.
      e.target.value = '';
    });
  }

  function attachClearHandler() {
    document.querySelector('#f-clear').addEventListener('click', () => {
      // Reset all filters; flip ticketsOnly OFF (so sold-out events also show);
      // preserve current sort. Reassigning rather than mutating so closures
      // captured by re-rendered handlers bind to the new object.
      state = {
        ...defaultState(),
        ticketsOnly: false,
        sortKey: state.sortKey,
        sortDir: state.sortDir,
      };
      ensureDefaultTypes();
      renderAllFilterUI();
      applyFilters();
    });
  }

  // Re-render every part of the filter UI. Used at initial mount, on popstate,
  // and after Clear. Keeps the three call sites from drifting (a single forgotten
  // populateMultiselect call here previously caused chips to vanish after
  // back/forward navigation).
  function renderAllFilterUI() {
    renderFilterRail(state, applyFilters);
    renderFriendsLists();
    populateMultiselect('f-types', uniqueTypes, state.types, applyFilters, typeLabels);
    populateMultiselect('f-locations', uniqueLocations, state.locations, applyFilters);
    renderResultsToolbar(state, applyFilters);
    attachLuckyHandler();
    attachClearHandler();
    attachScheduleHandlers();
    attachTypeBulkHandlers();
  }

  function attachTypeBulkHandlers() {
    // NOTE: mutate state.types in place rather than reassigning. The chip
    // click handler (set up by populateMultiselect) closes over the Set
    // reference passed to it; reassigning state.types here would leave
    // those closures pointing at an orphan Set.
    document.querySelector('#f-types-all').addEventListener('click', () => {
      state.types.clear();
      for (const t of uniqueTypes) state.types.add(t);
      for (const c of document.querySelectorAll('#f-types .chip')) c.classList.add('active');
      applyFilters();
    });
    document.querySelector('#f-types-none').addEventListener('click', () => {
      state.types.clear();
      for (const c of document.querySelectorAll('#f-types .chip')) c.classList.remove('active');
      applyFilters();
    });
  }

  // Strict-types semantics: an empty state.types means "show no events".
  // On initial load (or after Clear filters / popstate without explicit
  // types= in the hash), populate state.types with every known type so the
  // user starts with everything visible.
  function ensureDefaultTypes() {
    if (state.types.size === 0) state.types = new Set(uniqueTypes);
  }

  function applyFilters() {
    const saved = getSaved();
    const purchased = getPurchased();
    const overlapInfo = groupOverlapMap(blob.groups, saved, purchased);
    latestOverlap = overlapInfo;
    if (openGroup) {
      detailView.show(openGroup, overlapInfo.perSession, { allCollections: listCollections() });
    }
    const mineSaved = new Set([...saved, ...purchased]);
    const collections = listCollections();
    const pred = buildPredicate(state, mineSaved, collections);
    let visible = blob.groups.filter(pred);
    const hits = searchKeys(index, state.search);
    if (hits) visible = visible.filter(g => hits.has(g.key));
    visible.sort(compareGroups({ key: state.sortKey, dir: state.sortDir }));
    lastVisibleGroups = visible;
    const lucky = document.querySelector('#s-lucky');
    if (lucky) lucky.disabled = visible.length === 0;
    const savedBtn = document.querySelector('#s-saved');
    if (savedBtn) {
      savedBtn.textContent = `★ Saved (${saved.size})`;
      savedBtn.classList.toggle('active', state.mineActive);
    }
    const tlBtn = document.querySelector('#s-timeline');
    if (tlBtn) tlBtn.classList.toggle('active', state.viewMode === 'timeline');
    document.body.classList.toggle('timeline-on', state.viewMode === 'timeline');
    // List is always visible and always in sync with the predicate.
    const anySourceActive = state.mineActive || state.activeListIds.size > 0;
    const visibleCollections = anySourceActive
      ? collections.filter(c => state.activeListIds.has(c.id))
      : collections;
    tableView.setRows(visible, {
      saved,
      purchased,
      conflicts: latestOverlap.conflictedGroups,
      visibleCollections,
    });
    // Timeline is an additional side-by-side panel, toggled by viewMode.
    if (state.viewMode === 'timeline') {
      $('#results-timeline').classList.remove('hidden');
      const conflictedSessionIds = new Set(
        [...overlapInfo.perSession.entries()]
          .filter(([, info]) => !info.fits)
          .map(([sid]) => sid)
      );
      timelineView.render(
        blob.groups,
        saved,
        purchased,
        conflictedSessionIds,
        openGroup,
        visibleCollections,
      );
    } else {
      $('#results-timeline').classList.add('hidden');
    }
    $('#results-summary').textContent =
      `${visible.length.toLocaleString()} groups visible · ` +
      `${blob.meta.stats.matched.toLocaleString()} matched / ` +
      `${blob.meta.stats.unmatched.toLocaleString()} unmatched in dataset`;
    const hash = stateToHash(state, { allTypes: uniqueTypes });
    history.replaceState(null, '', hash ? `#${hash}` : '#');
    renderFriendsLists();
  }

  window.addEventListener('popstate', () => {
    state = hashToState(window.location.hash);
    ensureDefaultTypes();
    renderAllFilterUI();
    applyFilters();
  });

  // ── Import modal ──────────────────────────────────────────────────────────

  let pendingImportResult = null;

  function openImportModal(result, /* rawText */ _rawText) {
    const modal = document.querySelector('#import-modal');
    const backdrop = document.querySelector('#modal-backdrop');
    modal.querySelector('.summary').textContent =
      `${result.matched} sessions matched` +
      (result.missed ? `, ${result.missed} not found in current data` : '');
    pendingImportResult = result;

    // Populate the replace-list <select> with current collections.
    const select = modal.querySelector('#replace-list-select');
    select.innerHTML = '';
    for (const c of listCollections()) {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    }

    // Pre-fill the new-list-name input with the imported CSV's `name`.
    modal.querySelector('#new-list-name').value = result.name || '';

    // Smart default: pick the most appropriate action based on imported name and existing state.
    const radios = modal.querySelectorAll('input[name=import-action]');
    radios.forEach(r => r.checked = false);
    let defaultAction = 'replace-mine';
    if (result.name) {
      const existing = findByName(result.name);
      if (existing) {
        defaultAction = 'replace-list';
        select.value = existing.id;
      } else {
        defaultAction = 'new-list';
      }
    }
    modal.querySelector(`input[value=${defaultAction}]`).checked = true;

    modal.classList.remove('hidden');
    backdrop.classList.remove('hidden');
  }

  function closeImportModal() {
    document.querySelector('#import-modal').classList.add('hidden');
    document.querySelector('#modal-backdrop').classList.add('hidden');
    pendingImportResult = null;
  }

  document.querySelector('#import-modal .cancel-btn').addEventListener('click', closeImportModal);
  document.querySelector('#modal-backdrop').addEventListener('click', () => {
    closeImportModal();
    closeExportModal();
  });

  document.querySelector('#import-confirm').addEventListener('click', () => {
    if (!pendingImportResult) { closeImportModal(); return; }
    const action = document.querySelector('input[name=import-action]:checked')?.value;
    const r = pendingImportResult;
    const importedName = r.name || '';
    if (action === 'replace-mine') {
      replaceSaved(r.saved);
      replacePurchased(r.purchased);
      if (importedName) setMyName(importedName);
    } else if (action === 'add-mine') {
      const cur = getSaved();
      for (const id of r.saved) cur.add(id);
      replaceSaved(cur);
      const curP = getPurchased();
      for (const id of r.purchased) curP.add(id);
      replacePurchased(curP);
      if (importedName) setMyName(importedName);
    } else if (action === 'replace-list') {
      const id = document.querySelector('#replace-list-select').value;
      if (!id) { alert('No friend\'s list selected.'); return; }
      replaceCollection(id, {
        saved: [...r.saved],
        purchased: [...r.purchased],
        originalExportName: importedName,
      });
    } else if (action === 'new-list') {
      const name = document.querySelector('#new-list-name').value.trim();
      if (!name) { alert('Please enter a name for the new friend\'s list.'); return; }
      createCollection({
        name,
        saved: [...r.saved],
        purchased: [...r.purchased],
        originalExportName: importedName,
      });
    }
    closeImportModal();
    applyFilters();
  });

  // ── Export modal ──────────────────────────────────────────────────────────

  function openExportModal() {
    const modal = document.querySelector('#export-modal');
    const backdrop = document.querySelector('#modal-backdrop');
    const sources = modal.querySelector('#export-sources');
    const collections = listCollections();
    let html = `
      <label class="action-row">
        <input type="radio" name="export-source" value="mine" checked>
        <span>My events (saved: ${getSaved().size}, purchased: ${getPurchased().size})</span>
      </label>
    `;
    for (const c of collections) {
      html += `
        <label class="action-row">
          <input type="radio" name="export-source" value="${escapeAttr(c.id)}">
          <span><span class="swatch" style="background:${escapeAttr(c.color)};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px"></span>${escapeHtml(c.name)} (saved: ${c.saved.length}, purchased: ${c.purchased.length})</span>
        </label>
      `;
    }
    sources.innerHTML = html;
    const nameInput = modal.querySelector('#export-name');
    nameInput.value = getMyName();
    sources.querySelectorAll('input[name=export-source]').forEach(r => {
      r.addEventListener('change', () => {
        if (r.value === 'mine') nameInput.value = getMyName();
        else {
          const c = getCollection(r.value);
          nameInput.value = c ? c.name : '';
        }
      });
    });
    modal.classList.remove('hidden');
    backdrop.classList.remove('hidden');
  }

  function closeExportModal() {
    document.querySelector('#export-modal').classList.add('hidden');
    document.querySelector('#modal-backdrop').classList.add('hidden');
  }

  document.querySelector('#export-modal .cancel-btn').addEventListener('click', closeExportModal);

  document.querySelector('#export-confirm').addEventListener('click', () => {
    const sel = document.querySelector('input[name=export-source]:checked')?.value;
    const name = document.querySelector('#export-name').value.trim();
    let saved, purchased;
    if (sel === 'mine') {
      saved = getSaved();
      purchased = getPurchased();
    } else {
      const c = getCollection(sel);
      if (!c) return;
      saved = new Set(c.saved);
      purchased = new Set(c.purchased);
    }
    const csv = exportSchedule(blob.groups, saved, purchased, { name });
    const today = new Date().toISOString().slice(0, 10);
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const fname = slug
      ? `gencon-schedule-${slug}-${today}.csv`
      : `gencon-schedule-${today}.csv`;
    triggerDownload(fname, csv);
    closeExportModal();
  });

  // ─────────────────────────────────────────────────────────────────────────

  ensureDefaultTypes();
  renderAllFilterUI();
  applyFilters();
}

function escapeAttr(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formatDurH(h, isMax = false) {
  if (isMax && h >= 12) return '12h+';
  return `${h}h`;
}

main().catch((e) => {
  console.error(e);
  $('#results-summary').textContent = `Failed to load: ${e.message}`;
});
