import { loadData } from './data.js';
import { defaultState, buildPredicate, stateToHash, hashToState } from './filters.js';
import { buildIndex, searchKeys } from './search.js';
import { getSaved } from './saved.js';
import { createTableView } from './view-table.js';
import { createDetailView } from './view-detail.js';
import { KEY_OPTIONS, LABELS, compareGroups } from './sort.js';

const $ = (sel) => document.querySelector(sel);
const groupsByKey = new Map();

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
      <div class="label">Duration</div>
      <div id="f-durations">
        ${[['short','≤2h'],['med','2–4h'],['long','4h+']].map(([k,l]) => `<span class="chip ${state.durationBands.has(k)?'active':''}" data-duration="${k}">${l}</span>`).join('')}
      </div>
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
      <label><input type="checkbox" id="f-tournament" ${state.tournament==='yes'?'checked':''}> Tournament only</label><br>
      <label><input type="checkbox" id="f-saved" ${state.savedOnly?'checked':''}> Saved only</label>
    </div>
  `;
  $('#filter-rail').innerHTML = html;

  const wire = (id, evt, fn) => $(id).addEventListener(evt, (e) => { fn(e); onChange(); });
  wire('#f-search', 'input', (e) => state.search = e.target.value);
  wire('#f-hmin', 'input', (e) => state.hourMin = +e.target.value);
  wire('#f-hmax', 'input', (e) => state.hourMax = +e.target.value);
  wire('#f-party', 'input', (e) => state.party = +e.target.value || 0);
  wire('#f-cost', 'change', (e) => state.costBand = e.target.value);
  wire('#f-age', 'input', (e) => state.age = e.target.value);
  wire('#f-exp', 'input', (e) => state.experience = e.target.value);
  wire('#f-bgg', 'input', (e) => state.bggMin = +e.target.value);
  wire('#f-tix', 'change', (e) => state.ticketsOnly = e.target.checked);
  wire('#f-tournament', 'change', (e) => state.tournament = e.target.checked ? 'yes' : 'either');
  wire('#f-saved', 'change', (e) => state.savedOnly = e.target.checked);

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
  $('#f-durations').addEventListener('click', (e) => {
    const k = e.target.dataset.duration; if (!k) return;
    if (state.durationBands.has(k)) state.durationBands.delete(k); else state.durationBands.add(k);
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
    <div class="toolbar-right"></div>
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
}

function populateMultiselect(id, values, set, onChange) {
  const target = document.getElementById(id);
  target.innerHTML = values.map(v =>
    `<span class="chip ${set.has(v)?'active':''}" data-val="${escapeAttr(v)}">${escapeAttr(v)}</span>`
  ).join('');
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

  renderFilterRail(state, applyFilters);
  populateMultiselect(
    'f-types',
    [...new Set(blob.groups.map(g => g.event_type))].sort(),
    state.types,
    applyFilters,
  );
  populateMultiselect(
    'f-locations',
    [...new Set(blob.groups.map(g => g.sessions[0]?.location).filter(Boolean))].sort(),
    state.locations,
    applyFilters,
  );

  const tableView = createTableView({
    container: $('#results-list'),
    onRowClick: (key) => detailView.show(groupsByKey.get(key)),
  });
  const detailView = createDetailView({
    panel: $('#detail-panel'),
    shell: $('#app-shell'),
  });

  renderResultsToolbar(state, applyFilters);

  function applyFilters() {
    const saved = getSaved();
    const pred = buildPredicate(state, saved);
    let visible = blob.groups.filter(pred);
    const hits = searchKeys(index, state.search);
    if (hits) visible = visible.filter(g => hits.has(g.key));
    visible.sort(compareGroups({ key: state.sortKey, dir: state.sortDir }));
    tableView.setRows(visible);
    $('#results-summary').textContent =
      `${visible.length.toLocaleString()} groups visible · ` +
      `${blob.meta.stats.matched.toLocaleString()} matched / ` +
      `${blob.meta.stats.unmatched.toLocaleString()} unmatched in dataset`;
    const hash = stateToHash(state);
    history.replaceState(null, '', hash ? `#${hash}` : '#');
  }

  window.addEventListener('popstate', () => {
    state = hashToState(window.location.hash);
    renderFilterRail(state, applyFilters);
    renderResultsToolbar(state, applyFilters);
    applyFilters();
  });

  applyFilters();
}

function escapeAttr(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

main().catch((e) => {
  console.error(e);
  $('#results-summary').textContent = `Failed to load: ${e.message}`;
});
