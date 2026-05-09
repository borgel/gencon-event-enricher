// Tiny localStorage-backed sets of session IDs (s.gencon_id). Two
// independent flags: `saved` (interest/wishlist) and `purchased` (tickets
// bought). They're orthogonal — one does not imply the other.
//
// v2 switched from group keys to session IDs so users can mark individual
// sessions (e.g., "Dixit Thu 9am" but not "Dixit Fri 2pm"). v1 entries are
// abandoned in localStorage; harmless dead data.

const SAVED_KEY = 'gencon-enricher.saved.v2';
const PURCHASED_KEY = 'gencon-enricher.purchased.v2';

function read(key) {
  try {
    const arr = JSON.parse(localStorage.getItem(key) ?? '[]');
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}
function write(key, set) {
  localStorage.setItem(key, JSON.stringify([...set]));
}

export function getSaved() { return read(SAVED_KEY); }
export function isSaved(key) { return read(SAVED_KEY).has(key); }
export function toggleSaved(key) {
  const s = read(SAVED_KEY);
  if (s.has(key)) s.delete(key); else s.add(key);
  write(SAVED_KEY, s);
  return s.has(key);
}

export function getPurchased() { return read(PURCHASED_KEY); }
export function isPurchased(key) { return read(PURCHASED_KEY).has(key); }
export function togglePurchased(key) {
  const s = read(PURCHASED_KEY);
  if (s.has(key)) s.delete(key); else s.add(key);
  write(PURCHASED_KEY, s);
  return s.has(key);
}
