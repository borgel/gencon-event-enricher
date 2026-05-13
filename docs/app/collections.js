// Storage and CRUD for "friend's lists" — named collections of saved/purchased
// session IDs imported from CSVs. Mine stays in saved.js; this module is for
// the friends-of-the-user buckets only.
//
// Each collection has a stable id ('c-' + 8 hex), a user-renameable name, and
// a stable color picked from FRIEND_PALETTE at create time. Colors persist
// across reload and are never recomputed; deleting a collection frees its
// palette slot for the next new import.

export const MINE_COLOR = '#4a6cf7';
export const FRIEND_PALETTE = [
  '#e76f51', '#2a9d8f', '#f4a261', '#9b5de5', '#00bbf9', '#f15bb5',
];

export const COLLECTIONS_KEY = 'gencon-enricher.collections.v1';
export const MY_NAME_KEY = 'gencon-enricher.my-name.v1';

// Accept either #abc or #aabbcc forms; case-insensitive.
const HEX_COLOR_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export function isValidColor(s) {
  return typeof s === 'string' && HEX_COLOR_RE.test(s);
}

function readAll() {
  let arr;
  try {
    arr = JSON.parse(localStorage.getItem(COLLECTIONS_KEY) ?? '[]');
  } catch {
    return [];
  }
  if (!Array.isArray(arr)) return [];
  // Sanitize any collection whose stored color is missing or invalid (e.g.,
  // hand-edited localStorage). Reassign deterministically from the palette so
  // downstream render sites can trust c.color without escaping.
  const usedValid = arr.filter(c => isValidColor(c?.color)).map(c => c.color);
  let mutated = false;
  for (const c of arr) {
    if (!c || isValidColor(c.color)) continue;
    c.color = assignNextColor(usedValid);
    usedValid.push(c.color);
    mutated = true;
  }
  if (mutated) writeAll(arr);
  return arr;
}

function writeAll(arr) {
  localStorage.setItem(COLLECTIONS_KEY, JSON.stringify(arr));
}

export function listCollections() {
  return readAll().slice().sort((a, b) => (a.importedAt || '').localeCompare(b.importedAt || ''));
}

export function getCollection(id) {
  return readAll().find(c => c.id === id) ?? null;
}

export function makeCollectionId() {
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return 'c-' + [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
}

// Hash a string into [0, n). Stable across loads.
function hashIndex(s, n) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % n);
}

export function assignNextColor(existingColors) {
  const used = new Set(existingColors);
  for (const c of FRIEND_PALETTE) {
    if (!used.has(c)) return c;
  }
  // Palette exhausted. Deterministically pick a slot by hashing the existing
  // colors so the answer is stable across calls with the same input.
  const salt = [...used].sort().join('|');
  return FRIEND_PALETTE[hashIndex(salt, FRIEND_PALETTE.length)];
}

export function createCollection({ name, saved, purchased, originalExportName }) {
  const all = readAll();
  const id = makeCollectionId();
  const color = assignNextColor(all.map(c => c.color));
  const c = {
    id,
    name: name || originalExportName || 'Untitled',
    color,
    saved: [...(saved || [])],
    purchased: [...(purchased || [])],
    importedAt: new Date().toISOString(),
    originalExportName: originalExportName || '',
  };
  all.push(c);
  writeAll(all);
  return c;
}

export function replaceCollection(id, { name, saved, purchased, originalExportName }) {
  const all = readAll();
  const i = all.findIndex(c => c.id === id);
  if (i < 0) return null;
  const prev = all[i];
  const updated = {
    ...prev,
    name: name ?? prev.name,
    saved: [...(saved || [])],
    purchased: [...(purchased || [])],
    importedAt: new Date().toISOString(),
    originalExportName: originalExportName ?? prev.originalExportName,
  };
  all[i] = updated;
  writeAll(all);
  return updated;
}

export function renameCollection(id, name) {
  const all = readAll();
  const i = all.findIndex(c => c.id === id);
  if (i < 0) return null;
  all[i] = { ...all[i], name };
  writeAll(all);
  return all[i];
}

export function deleteCollection(id) {
  const all = readAll();
  const i = all.findIndex(c => c.id === id);
  if (i < 0) return false;
  all.splice(i, 1);
  writeAll(all);
  return true;
}

export function findByName(name) {
  if (!name) return null;
  const needle = name.trim().toLowerCase();
  const all = readAll();
  return all.find(c =>
    (c.name || '').trim().toLowerCase() === needle ||
    (c.originalExportName || '').trim().toLowerCase() === needle,
  ) ?? null;
}

export function getMyName() {
  return localStorage.getItem(MY_NAME_KEY) ?? '';
}

export function setMyName(name) {
  if (!name) localStorage.removeItem(MY_NAME_KEY);
  else localStorage.setItem(MY_NAME_KEY, name);
}
