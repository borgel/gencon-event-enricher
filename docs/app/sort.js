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

// Returns a comparator suitable for Array.prototype.sort.
//
// - 'start': lexicographic compare of ISO start strings (correct for ISO-8601).
// - 'type':  localeCompare on event_type_label (NOT the abbreviation).
// - 'bgg':   numeric compare on bgg.bayesaverage; nulls always last regardless
//            of direction (rating-less rows fall to the bottom).
//
// Tiebreaker for 'type' and 'bgg' is start ascending, so visually-equal rows
// have a stable, perceptible order.
export function compareGroups(state) {
  const dirMul = state.dir === 'desc' ? -1 : 1;
  return (a, b) => {
    let primary = 0;
    if (state.key === 'start') {
      primary = compareStart(a, b) * dirMul;
    } else if (state.key === 'type') {
      const al = a.event_type_label ?? '';
      const bl = b.event_type_label ?? '';
      primary = al.localeCompare(bl) * dirMul;
    } else if (state.key === 'bgg') {
      const av = a.bgg?.bayesaverage ?? null;
      const bv = b.bgg?.bayesaverage ?? null;
      // Nulls always last, regardless of direction.
      if (av == null && bv == null) primary = 0;
      else if (av == null) primary = 1;
      else if (bv == null) primary = -1;
      else primary = (av - bv) * dirMul;
    }
    if (primary !== 0) return primary;
    // Secondary: start ascending. (For start key, this is a no-op.)
    return compareStart(a, b);
  };
}

function compareStart(a, b) {
  const as = a.sessions?.[0]?.start ?? '';
  const bs = b.sessions?.[0]?.start ?? '';
  if (as === bs) return 0;
  return as < bs ? -1 : 1;
}
