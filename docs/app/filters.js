// Filter state shape (all optional / null = no filter):
//   { search, days: Set<'thu'|'fri'|'sat'|'sun'>, hourMin, hourMax,
//     types: Set<string>, durationBands: Set<'short'|'med'|'long'>,
//     party, costBand, age, experience, ticketsOnly, tournament,
//     locations: Set<string>, bggMin, hasBggOnly, savedOnly }

export function defaultState() {
  return {
    search: '',
    days: new Set(),
    hourMin: 0, hourMax: 24,
    types: new Set(),
    durationBands: new Set(),
    party: 0,
    costBand: '',         // '', '0', '0-10', '10+'
    age: '',
    experience: '',
    ticketsOnly: true,
    tournament: 'either', // 'either'|'yes'|'no'
    locations: new Set(),
    bggMin: 0,
    hasBggOnly: false,
    savedOnly: false,
  };
}

const DAY_FROM_DATE = new Date('2026-07-30T00:00:00').getDay(); // tweak per year if needed
const DAY_INDEX = { thu: 0, fri: 1, sat: 2, sun: 3 };

function dayKeyFromDate(d) {
  // GenCon 2026 is Thu 2026-07-30 through Sun 2026-08-02.
  const y = d.getFullYear(), m = d.getMonth(), day = d.getDate();
  if (y === 2026 && m === 6 && day === 30) return 'thu';
  if (y === 2026 && m === 6 && day === 31) return 'fri';
  if (y === 2026 && m === 7 && day === 1) return 'sat';
  if (y === 2026 && m === 7 && day === 2) return 'sun';
  return null;
}

function durationBand(minutes) {
  if (minutes == null) return null;
  if (minutes <= 120) return 'short';
  if (minutes <= 240) return 'med';
  return 'long';
}

function costBandOf(cost) {
  if (cost == null) return '';
  if (cost === 0) return '0';
  if (cost <= 10) return '0-10';
  return '10+';
}

export function buildPredicate(state, savedKeys) {
  return (g) => {
    if (state.savedOnly && !savedKeys.has(g.key)) return false;
    if (state.hasBggOnly && !g.bgg) return false;
    if (state.bggMin > 0) {
      if (!g.bgg || (g.bgg.bayesaverage ?? 0) < state.bggMin) return false;
    }
    if (state.types.size && !state.types.has(g.event_type)) return false;
    if (state.locations.size && !state.locations.has(matchLocation(g))) return false;
    if (state.tournament !== 'either') {
      const want = state.tournament === 'yes';
      if (g.tournament !== want) return false;
    }
    if (state.age && g.age_required !== state.age) return false;
    if (state.experience && g.experience_required !== state.experience) return false;
    if (state.party > 0) {
      if (g.min_players != null && g.min_players > state.party) return false;
      if (g.max_players != null && g.max_players < state.party) return false;
    }
    if (state.costBand && costBandOf(g.cost) !== state.costBand) return false;
    if (state.durationBands.size && !state.durationBands.has(durationBand(g.duration_minutes))) return false;

    // Sessions-aware filters: if any session passes, the group passes.
    const dayCheck = state.days.size > 0;
    const hourCheck = state.hourMin > 0 || state.hourMax < 24;
    const ticketsCheck = state.ticketsOnly;
    if (dayCheck || hourCheck || ticketsCheck) {
      const ok = g.sessions.some((s) => {
        if (ticketsCheck && (s.tickets_available ?? 0) <= 0) return false;
        if (dayCheck && !state.days.has(dayKeyFromDate(new Date(s.start)))) return false;
        if (hourCheck) {
          const h = new Date(s.start).getHours();
          if (h < state.hourMin || h >= state.hourMax) return false;
        }
        return true;
      });
      if (!ok) return false;
    }

    if (state.search) {
      // Search is layered later via MiniSearch; here we just respect it as a no-op.
    }
    return true;
  };
}

function matchLocation(g) {
  return g.sessions[0]?.location ?? '';
}

// ---- URL hash sync ----
//
// Encoded form is `key=value&key=value`. Sets are comma-separated. Empty
// values are omitted to keep URLs short.

const SET_KEYS = ['days', 'types', 'durationBands', 'locations'];

export function stateToHash(state) {
  const parts = [];
  if (state.search) parts.push(`q=${encodeURIComponent(state.search)}`);
  for (const k of SET_KEYS) {
    if (state[k].size) parts.push(`${k}=${[...state[k]].join(',')}`);
  }
  if (state.hourMin > 0)  parts.push(`hMin=${state.hourMin}`);
  if (state.hourMax < 24) parts.push(`hMax=${state.hourMax}`);
  if (state.party > 0)    parts.push(`party=${state.party}`);
  if (state.costBand)     parts.push(`cost=${state.costBand}`);
  if (state.age)          parts.push(`age=${encodeURIComponent(state.age)}`);
  if (state.experience)   parts.push(`exp=${encodeURIComponent(state.experience)}`);
  if (!state.ticketsOnly) parts.push(`tix=0`);    // default is true → omit when on
  if (state.tournament !== 'either') parts.push(`tourn=${state.tournament}`);
  if (state.bggMin > 0)   parts.push(`bgg=${state.bggMin}`);
  if (state.hasBggOnly)   parts.push(`bggOnly=1`);
  if (state.savedOnly)    parts.push(`saved=1`);
  return parts.join('&');
}

export function hashToState(hash) {
  const s = defaultState();
  if (!hash) return s;
  const trimmed = hash.startsWith('#') ? hash.slice(1) : hash;
  for (const pair of trimmed.split('&').filter(Boolean)) {
    const [k, v] = pair.split('=');
    const dv = decodeURIComponent(v ?? '');
    switch (k) {
      case 'q': s.search = dv; break;
      case 'days': case 'types': case 'durationBands': case 'locations':
        s[k] = new Set(dv.split(',').filter(Boolean)); break;
      case 'hMin': s.hourMin = +dv; break;
      case 'hMax': s.hourMax = +dv; break;
      case 'party': s.party = +dv; break;
      case 'cost': s.costBand = dv; break;
      case 'age': s.age = dv; break;
      case 'exp': s.experience = dv; break;
      case 'tix': s.ticketsOnly = dv !== '0'; break;
      case 'tourn': s.tournament = dv; break;
      case 'bgg': s.bggMin = +dv; break;
      case 'bggOnly': s.hasBggOnly = dv === '1'; break;
      case 'saved': s.savedOnly = dv === '1'; break;
    }
  }
  return s;
}
