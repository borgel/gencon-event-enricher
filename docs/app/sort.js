// Sort state and helpers for the events list.
//
// Sort is conceptually distinct from filters: it changes ORDER, never
// VISIBILITY. State shape: { key: 'start'|'type'|'bgg', dir: 'asc'|'desc' }.

export function defaultSortState() {
  return { key: 'start', dir: 'asc' };
}

export const KEY_OPTIONS = [
  ['start', 'Start time'],
  ['type',  'Event type'],
  ['bgg',   'BGG rating'],
];

export const LABELS = {
  start: { asc: '↑ Earliest first', desc: '↓ Latest first' },
  type:  { asc: '↑ A → Z',           desc: '↓ Z → A' },
  bgg:   { asc: '↑ Lowest first',    desc: '↓ Highest first' },
};

const VALID_KEYS = new Set(['start', 'type', 'bgg']);
const VALID_DIRS = new Set(['asc', 'desc']);

// Encode non-default sort state to URL hash fragment(s). Returns '' when default.
export function sortStateToHash(state) {
  const def = defaultSortState();
  const parts = [];
  if (state.key !== def.key) parts.push(`sort=${encodeURIComponent(state.key)}`);
  if (state.dir !== def.dir) parts.push(`dir=${encodeURIComponent(state.dir)}`);
  return parts.join('&');
}

// Apply a single hash key/value pair to a state object in place. Ignored if
// not a sort key or if the value is invalid. Used by filters.hashToState which
// iterates all key/value pairs.
export function applyHashPair(state, key, value) {
  if (key === 'sort' && VALID_KEYS.has(value)) state.key = value;
  else if (key === 'dir' && VALID_DIRS.has(value)) state.dir = value;
}
