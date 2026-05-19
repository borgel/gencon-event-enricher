// Modal lifecycle for import / export / manage friends' lists.
//
// main.js calls installModals(deps) once on startup; thereafter every
// file-input change, button click, backdrop click, and per-modal
// cancel/confirm listener lives here. The transient `pendingImportResult`
// (set on file pick, consumed on confirm) is scoped to this module rather
// than leaking to main.js.
//
// Public surface:
//   - installModals(deps): wire all DOM listeners. Call once.
//   - openManageModal(): used by main.js when the rail's "Manage…" link is
//     clicked. (Re-bound on every rail render.)

import {
  parseScheduleCSV, exportSchedule, triggerDownload,
  encodeBlob, decodeBlob,
} from './schedule.js';
import {
  listCollections, createCollection, replaceCollection, findByName,
  getMyName, setMyName, getCollection,
  renameCollection, deleteCollection,
} from './collections.js';
import {
  getSaved, getPurchased, replaceSaved, replacePurchased,
} from './saved.js';

let pendingImportResult = null;
let deps = null;

/**
 * deps:
 *   blob               — the loaded events blob; modals read blob.groups for export.
 *   applyFilters()     — re-renders rail + list + timeline.
 *   renderFriendsLists() — re-renders the rail's Friend's Lists section.
 *   getState()         — returns the current filter state (state.activeListIds
 *                        is mutated on delete). Getter rather than direct ref
 *                        because main.js reassigns `state` on Clear filters.
 */
export function installModals(_deps) {
  deps = _deps;

  document.querySelector('#f-import').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    const result = parseScheduleCSV(text, deps.blob.groups);
    openImportModal(result);
    // Reset so the same file can be re-selected later.
    e.target.value = '';
  });

  document.querySelector('#f-export').addEventListener('click', openExportModal);

  document.querySelector('#import-modal .cancel-btn').addEventListener('click', closeImportModal);
  document.querySelector('#export-modal .cancel-btn').addEventListener('click', closeExportModal);
  document.querySelector('#manage-modal .cancel-btn').addEventListener('click', closeManageModal);

  document.querySelector('#modal-backdrop').addEventListener('click', () => {
    closeImportModal();
    closeExportModal();
    closeManageModal();
    closeShareModal();
    closePasteModal();
  });

  document.querySelector('#import-confirm').addEventListener('click', confirmImport);
  document.querySelector('#export-confirm').addEventListener('click', confirmExport);

  document.querySelector('#share-modal .cancel-btn').addEventListener('click', closeShareModal);
  document.querySelector('#paste-modal .cancel-btn').addEventListener('click', closePasteModal);
  document.querySelector('#share-copy').addEventListener('click', copyShareBlob);
  document.querySelector('#paste-decode').addEventListener('click', decodePasteBlob);
}

// ── Import ────────────────────────────────────────────────────────────────

function openImportModal(result) {
  const modal = document.querySelector('#import-modal');
  const backdrop = document.querySelector('#modal-backdrop');
  modal.querySelector('.summary').textContent =
    `${result.matched} sessions matched` +
    (result.missed ? `, ${result.missed} not found in current data` : '');
  pendingImportResult = result;

  const select = modal.querySelector('#replace-list-select');
  select.innerHTML = '';
  for (const c of listCollections()) {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    select.appendChild(opt);
  }

  modal.querySelector('#new-list-name').value = result.name || '';

  // Smart default: name matches existing list → replace it; name with no
  // match → new list (pre-filled); no name → replace mine.
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

function confirmImport() {
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
    if (!id) { alert("No friend's list selected."); return; }
    replaceCollection(id, {
      saved: [...r.saved],
      purchased: [...r.purchased],
      originalExportName: importedName,
    });
  } else if (action === 'new-list') {
    const name = document.querySelector('#new-list-name').value.trim();
    if (!name) { alert("Please enter a name for the new friend's list."); return; }
    createCollection({
      name,
      saved: [...r.saved],
      purchased: [...r.purchased],
      originalExportName: importedName,
    });
  }
  closeImportModal();
  deps.applyFilters();
}

// ── Export ────────────────────────────────────────────────────────────────

// Renders the source picker (Mine + each friend's list) into `container`
// using the radio group name `radioName`. Calls `onSelect(sourceValue)`
// whenever the selection changes; the value is 'mine' or a collection id.
function renderExportSources(container, radioName, onSelect) {
  const collections = listCollections();
  let html = `
    <label class="action-row">
      <input type="radio" name="${escapeAttr(radioName)}" value="mine" checked>
      <span>My events (saved: ${getSaved().size}, purchased: ${getPurchased().size})</span>
    </label>
  `;
  for (const c of collections) {
    html += `
      <label class="action-row">
        <input type="radio" name="${escapeAttr(radioName)}" value="${escapeAttr(c.id)}">
        <span><span class="swatch" style="background:${escapeAttr(c.color)};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px"></span>${escapeHtml(c.name)} (saved: ${c.saved.length}, purchased: ${c.purchased.length})</span>
      </label>
    `;
  }
  container.innerHTML = html;
  container.querySelectorAll(`input[name=${radioName}]`).forEach(r => {
    r.addEventListener('change', () => { if (r.checked) onSelect(r.value); });
  });
}

// Returns the {saved, purchased} sets for a source value ('mine' or a
// collection id). Returns null if the collection is gone.
function getSourceSets(sourceValue) {
  if (sourceValue === 'mine') {
    return { saved: getSaved(), purchased: getPurchased() };
  }
  const c = getCollection(sourceValue);
  if (!c) return null;
  return { saved: new Set(c.saved), purchased: new Set(c.purchased) };
}

function openExportModal() {
  const modal = document.querySelector('#export-modal');
  const backdrop = document.querySelector('#modal-backdrop');
  const sources = modal.querySelector('#export-sources');
  const nameInput = modal.querySelector('#export-name');
  nameInput.value = getMyName();
  renderExportSources(sources, 'export-source', (value) => {
    if (value === 'mine') nameInput.value = getMyName();
    else {
      const c = getCollection(value);
      nameInput.value = c ? c.name : '';
    }
  });
  modal.classList.remove('hidden');
  backdrop.classList.remove('hidden');
}

function closeExportModal() {
  document.querySelector('#export-modal').classList.add('hidden');
  document.querySelector('#modal-backdrop').classList.add('hidden');
}

function confirmExport() {
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
  const csv = exportSchedule(deps.blob.groups, saved, purchased, { name });
  const today = new Date().toISOString().slice(0, 10);
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const fname = slug
    ? `gencon-schedule-${slug}-${today}.csv`
    : `gencon-schedule-${today}.csv`;
  triggerDownload(fname, csv);
  closeExportModal();
}

// ── Share (base64 blob export) ────────────────────────────────────────────

// Increments on every regenerate; lets us drop stale async results when
// the user changes source/name before the previous encode resolves.
let shareGen = 0;

export function openShareModal() {
  const modal = document.querySelector('#share-modal');
  const backdrop = document.querySelector('#modal-backdrop');
  const sources = modal.querySelector('#share-sources');
  const nameInput = modal.querySelector('#share-name');
  const statusEl = modal.querySelector('#share-copied-status');
  statusEl.textContent = '';
  nameInput.value = getMyName();

  let currentSource = 'mine';
  renderExportSources(sources, 'share-source', (value) => {
    currentSource = value;
    if (value === 'mine') nameInput.value = getMyName();
    else {
      const c = getCollection(value);
      nameInput.value = c ? c.name : '';
    }
    regenerateShareBlob(currentSource, nameInput.value.trim());
  });
  nameInput.addEventListener('input', () => {
    regenerateShareBlob(currentSource, nameInput.value.trim());
  });

  regenerateShareBlob(currentSource, nameInput.value.trim());
  modal.classList.remove('hidden');
  backdrop.classList.remove('hidden');
}

async function regenerateShareBlob(sourceValue, name) {
  const textarea = document.querySelector('#share-blob');
  const sets = getSourceSets(sourceValue);
  if (!sets) { textarea.value = ''; return; }
  const gen = ++shareGen;
  const csv = exportSchedule(deps.blob.groups, sets.saved, sets.purchased, { name });
  const blob = await encodeBlob(csv);
  if (gen !== shareGen) return;  // a newer generation has started
  textarea.value = blob;
}

function closeShareModal() {
  document.querySelector('#share-modal').classList.add('hidden');
  document.querySelector('#modal-backdrop').classList.add('hidden');
}

async function copyShareBlob() {
  const textarea = document.querySelector('#share-blob');
  const statusEl = document.querySelector('#share-copied-status');
  const value = textarea.value;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    statusEl.textContent = 'Copied!';
    setTimeout(() => { statusEl.textContent = ''; }, 1500);
  } catch {
    // Fallback for browsers without clipboard permission: select the textarea
    // so the user can Cmd-C / Ctrl-C themselves.
    textarea.removeAttribute('readonly');
    textarea.focus();
    textarea.select();
    textarea.setAttribute('readonly', '');
    statusEl.textContent = 'Press Cmd-C / Ctrl-C to copy.';
  }
}

// ── Paste (base64 blob import) ────────────────────────────────────────────

export function openPasteModal() {
  const modal = document.querySelector('#paste-modal');
  const backdrop = document.querySelector('#modal-backdrop');
  modal.querySelector('#paste-blob').value = '';
  setPasteError('');
  modal.classList.remove('hidden');
  backdrop.classList.remove('hidden');
}

function closePasteModal() {
  document.querySelector('#paste-modal').classList.add('hidden');
  document.querySelector('#modal-backdrop').classList.add('hidden');
}

function setPasteError(msg) {
  const el = document.querySelector('#paste-error');
  if (!msg) { el.textContent = ''; el.classList.add('hidden'); return; }
  el.textContent = msg;
  el.classList.remove('hidden');
}

async function decodePasteBlob() {
  const text = document.querySelector('#paste-blob').value;
  if (!text.trim()) {
    setPasteError("Paste the shared text into the box first.");
    return;
  }
  const recovered = await decodeBlob(text);
  if (recovered == null) {
    if (!/GENCON1:/.test(text)) {
      setPasteError("Couldn't find a schedule blob in what you pasted. The text should start with `GENCON1:`.");
    } else {
      setPasteError("The blob looks corrupted — try copying it again from the source.");
    }
    return;
  }
  const result = parseScheduleCSV(recovered, deps.blob.groups);
  if (result.matched === 0 && result.missed === 0) {
    setPasteError("Decoded successfully but no sessions were found in the blob.");
    return;
  }
  closePasteModal();
  openImportModal(result);
}

// ── Manage ────────────────────────────────────────────────────────────────

export function openManageModal() {
  const modal = document.querySelector('#manage-modal');
  const backdrop = document.querySelector('#modal-backdrop');
  renderManageRows();
  modal.classList.remove('hidden');
  backdrop.classList.remove('hidden');
}

function closeManageModal() {
  document.querySelector('#manage-modal').classList.add('hidden');
  document.querySelector('#modal-backdrop').classList.add('hidden');
}

function renderManageRows() {
  const container = document.querySelector('#manage-rows');
  const collections = listCollections();
  if (collections.length === 0) {
    container.innerHTML = '<p class="muted">No friend\'s lists yet.</p>';
    return;
  }
  container.innerHTML = collections.map(c => {
    const imported = (c.importedAt || '').slice(0, 10);
    return `
      <div class="manage-row" data-id="${escapeAttr(c.id)}">
        <div class="manage-row-head">
          <span class="swatch" style="background:${escapeAttr(c.color)}"></span>
          <span class="name">${escapeHtml(c.name)}</span>
        </div>
        <div class="manage-row-meta">
          ${c.saved.length} saved, ${c.purchased.length} purchased · imported ${imported}
        </div>
        <div class="manage-row-actions">
          <button type="button" class="rename-btn">Rename</button>
          <button type="button" class="export-btn">Export</button>
          <button type="button" class="delete-btn">Delete</button>
        </div>
      </div>
    `;
  }).join('');
  container.querySelectorAll('.rename-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.target.closest('.manage-row').dataset.id;
      const cur = getCollection(id);
      const next = window.prompt('New name:', cur?.name || '');
      if (next == null) return;
      const trimmed = next.trim();
      if (!trimmed) return;
      renameCollection(id, trimmed);
      renderManageRows();
      deps.renderFriendsLists();
      deps.applyFilters();
    });
  });
  container.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.target.closest('.manage-row').dataset.id;
      const cur = getCollection(id);
      if (!window.confirm(`Delete "${cur?.name ?? id}"?`)) return;
      deleteCollection(id);
      deps.getState().activeListIds.delete(id);
      renderManageRows();
      deps.renderFriendsLists();
      deps.applyFilters();
    });
  });
  container.querySelectorAll('.export-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.target.closest('.manage-row').dataset.id;
      closeManageModal();
      openExportModal();
      const radio = document.querySelector(`input[name=export-source][value="${id}"]`);
      if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event('change'));
      }
    });
  });
}

// ── Local escapers (kept inline to avoid a shared escape module for now) ──

function escapeAttr(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
