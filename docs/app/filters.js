// Filter state shape (all optional / null = no filter):
//   { search, days: Set<'thu'|'fri'|'sat'|'sun'>, hourMin, hourMax,
//     types: Set<string>, durMinH, durMaxH,
//     party, costBand, age, experience, ticketsOnly, tournament,
//     locations: Set<string>, bggMin, bggMatch, mineActive, activeListIds: Set<string> }

import { applyHashPair as applySortHashPair, sortStateToHash } from './sort.js';

export function defaultState() {
  return {
    search: '',
    days: new Set(),
    hourMin: 0, hourMax: 24,
    types: new Set(),
    durMinH: 0, durMaxH: 12,
    party: 0,
    costBand: '',         // '', '0', '0-10', '10+'
    age: '',
    experience: '',
    ticketsOnly: true,
    tournament: 'either', // 'either'|'yes'|'no'
    locations: new Set(),
    bggMin: 0,
    bggMatch: 'either',  // 'either'|'yes'|'no'
    mineActive: false,
    activeListIds: new Set(),
    sortKey: 'start',
    sortDir: 'asc',
    viewMode: 'list',
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

function costBandOf(cost) {
  if (cost == null) return '';
  if (cost === 0) return '0';
  if (cost <= 10) return '0-10';
  return '10+';
}

// state.mineActive + state.activeListIds drive the union saved-filter.
// mineSaved is Mine's union of saved + purchased session IDs.
// collections is the array from listCollections().
export function buildPredicate(state, mineSaved, collections) {
  const activeListIds = state.activeListIds;
  const activeLists = (collections || []).filter(c => activeListIds.has(c.id));
  const anySourceActive = state.mineActive || activeLists.length > 0;

  return (g) => {
    if (anySourceActive) {
      const matches = g.sessions.some((s) => {
        if (state.mineActive && mineSaved.has(s.gencon_id)) return true;
        for (const c of activeLists) {
          if (c.saved.includes(s.gencon_id)) return true;
          if (c.purchased.includes(s.gencon_id)) return true;
        }
        return false;
      });
      if (!matches) return false;
    }

    if (state.bggMatch === 'yes' && !g.bgg) return false;
    if (state.bggMatch === 'no'  && g.bgg)  return false;
    if (state.bggMin > 0) {
      if (!g.bgg || (g.bgg.bayesaverage ?? 0) < state.bggMin) return false;
    }
    if (!state.types.has(g.event_type)) return false;
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
    if (state.durMinH > 0 || state.durMaxH < 12) {
      const h = (g.duration_minutes ?? 0) / 60;
      if (h < state.durMinH) return false;
      if (state.durMaxH < 12 && h > state.durMaxH) return false;
    }

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
      // Search is layered later via MiniSearch.
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

const SET_KEYS = ['days', 'types', 'locations'];

// `options.allTypes` (optional) is the full set of event types in the dataset.
// When state.types contains every entry, the `types=` fragment is omitted to
// keep URLs short for the common "all selected" default.
export function stateToHash(state, options = {}) {
  const parts = [];
  if (state.search) parts.push(`q=${encodeURIComponent(state.search)}`);
  for (const k of SET_KEYS) {
    if (!state[k].size) continue;
    if (k === 'types' && options.allTypes && state.types.size === options.allTypes.length
        && options.allTypes.every(t => state.types.has(t))) {
      continue;
    }
    parts.push(`${k}=${[...state[k]].join(',')}`);
  }
  if (state.hourMin > 0)  parts.push(`hMin=${state.hourMin}`);
  if (state.hourMax < 24) parts.push(`hMax=${state.hourMax}`);
  if (state.durMinH > 0)  parts.push(`durMin=${state.durMinH}`);
  if (state.durMaxH < 12) parts.push(`durMax=${state.durMaxH}`);
  if (state.party > 0)    parts.push(`party=${state.party}`);
  if (state.costBand)     parts.push(`cost=${state.costBand}`);
  if (state.age)          parts.push(`age=${encodeURIComponent(state.age)}`);
  if (state.experience)   parts.push(`exp=${encodeURIComponent(state.experience)}`);
  if (!state.ticketsOnly) parts.push(`tix=0`);    // default is true → omit when on
  if (state.tournament !== 'either') parts.push(`tourn=${state.tournament}`);
  if (state.bggMin > 0)   parts.push(`bgg=${state.bggMin}`);
  if (state.bggMatch !== 'either') parts.push(`bggMatch=${state.bggMatch}`);
  if (state.mineActive)   parts.push(`saved=1`);
  if (state.activeListIds.size) parts.push(`lists=${[...state.activeListIds].join(',')}`);
  const sortFrag = sortStateToHash({ key: state.sortKey, dir: state.sortDir });
  if (sortFrag) parts.push(sortFrag);
  if (state.viewMode === 'timeline') parts.push('view=timeline');
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
      case 'days': case 'types': case 'locations':
        s[k] = new Set(dv.split(',').filter(Boolean)); break;
      case 'hMin': s.hourMin = +dv; break;
      case 'hMax': s.hourMax = +dv; break;
      case 'durMin': s.durMinH = +dv; break;
      case 'durMax': s.durMaxH = +dv; break;
      case 'party': s.party = +dv; break;
      case 'cost': s.costBand = dv; break;
      case 'age': s.age = dv; break;
      case 'exp': s.experience = dv; break;
      case 'tix': s.ticketsOnly = dv !== '0'; break;
      case 'tourn': s.tournament = dv; break;
      case 'bgg': s.bggMin = +dv; break;
      case 'bggMatch':
        if (dv === 'yes' || dv === 'no' || dv === 'either') s.bggMatch = dv;
        break;
      case 'saved': s.mineActive = dv === '1'; break;
      case 'lists': s.activeListIds = new Set(dv.split(',').filter(Boolean)); break;
      case 'view':
        if (dv === 'timeline' || dv === 'list') s.viewMode = dv;
        break;
      case 'sort':
      case 'dir': {
        const tmp = { key: s.sortKey, dir: s.sortDir };
        applySortHashPair(tmp, k, dv);
        s.sortKey = tmp.key; s.sortDir = tmp.dir;
        break;
      }
    }
  }
  return s;
}
