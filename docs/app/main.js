import { loadData } from './data.js';
import { defaultState, buildPredicate, stateToHash, hashToState } from './filters.js';
import { buildIndex, searchKeys } from './search.js';
import { getSaved, getPurchased, replaceSaved, replacePurchased } from './saved.js';
import { exportSchedule, parseScheduleCSV, triggerDownload } from './schedule.js';
import { createTableView } from './view-table.js';
import { createDetailView } from './view-detail.js';
import { KEY_OPTIONS, LABELS, compareGroups } from './sort.js';

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
      <button id="s-saved" type="button" class="${state.savedOnly ? 'active' : ''}">★ Saved (0)</button>
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
    state.savedOnly = !state.savedOnly;
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
  for (const g of blob.groups) groupsByKey.set(g.key, g);

  let state = hashToState(window.location.hash);
  const index = buildIndex(blob.groups);

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
    onRowClick: (key) => detailView.show(groupsByKey.get(key)),
  });
  const detailView = createDetailView({
    panel: $('#detail-panel'),
    onChange: () => applyFilters(),
  });

  function attachLuckyHandler() {
    document.querySelector('#s-lucky').addEventListener('click', () => {
      if (!lastVisibleGroups.length) return;
      const g = lastVisibleGroups[Math.floor(Math.random() * lastVisibleGroups.length)];
      detailView.show(g);
      tableView.scrollToKey(g.key);
      tableView.setSelectedKey(g.key);
    });
  }

  function attachScheduleHandlers() {
    document.querySelector('#f-export').addEventListener('click', () => {
      const csv = exportSchedule(blob.groups, getSaved(), getPurchased());
      const today = new Date().toISOString().slice(0, 10);
      triggerDownload(`gencon-schedule-${today}.csv`, csv);
    });
    document.querySelector('#f-import').addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const text = await file.text();
      const result = parseScheduleCSV(text, blob.groups);
      const summary = `${result.matched} sessions matched` +
        (result.missed ? `, ${result.missed} not found in current data` : '');
      const ok = window.confirm(
        `Import schedule?\n\n${summary}.\n\n` +
        `This will replace your current Saved and Purchased state.`,
      );
      if (ok) {
        replaceSaved(result.saved);
        replacePurchased(result.purchased);
        applyFilters();
      }
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
    populateMultiselect('f-types', uniqueTypes, state.types, applyFilters, typeLabels);
    populateMultiselect('f-locations', uniqueLocations, state.locations, applyFilters);
    renderResultsToolbar(state, applyFilters);
    attachLuckyHandler();
    attachClearHandler();
    attachScheduleHandlers();
  }

  renderAllFilterUI();

  function applyFilters() {
    const saved = getSaved();
    const purchased = getPurchased();
    const pred = buildPredicate(state, saved);
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
      savedBtn.classList.toggle('active', state.savedOnly);
    }
    tableView.setRows(visible, { saved, purchased });
    $('#results-summary').textContent =
      `${visible.length.toLocaleString()} groups visible · ` +
      `${blob.meta.stats.matched.toLocaleString()} matched / ` +
      `${blob.meta.stats.unmatched.toLocaleString()} unmatched in dataset`;
    const hash = stateToHash(state);
    history.replaceState(null, '', hash ? `#${hash}` : '#');
  }

  window.addEventListener('popstate', () => {
    state = hashToState(window.location.hash);
    renderAllFilterUI();
    applyFilters();
  });

  applyFilters();
}

function escapeAttr(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
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
