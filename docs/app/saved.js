// Tiny localStorage-backed set of saved event keys.

const KEY = 'gencon-enricher.saved.v1';

function read() {
  try {
    const arr = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}
function write(set) {
  localStorage.setItem(KEY, JSON.stringify([...set]));
}

export function getSaved() { return read(); }

export function isSaved(key) { return read().has(key); }

export function toggleSaved(key) {
  const s = read();
  if (s.has(key)) s.delete(key); else s.add(key);
  write(s);
  return s.has(key);
}
