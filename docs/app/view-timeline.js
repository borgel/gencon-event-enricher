// Vertical day-column timeline. Days are columns; hours 8a–midnight run top
// to bottom at HOUR_PX pixels per hour. Saved/purchased sessions render as
// solid blocks; preview sessions (the group whose detail panel is open)
// render as dashed yellow blocks.
//
// Lane packing: when sessions overlap in a day, the day column shows N
// side-by-side tracks. Track count drives the column's width.
//
// Out-of-window: sessions starting before 8a get a ← indicator at the top
// of the block; ending past midnight get a → indicator at the bottom.

import { assignTracks } from './conflict.js';

const HOUR_PX = 40;
const WINDOW_START_HOUR = 8;     // 8a
const WINDOW_END_HOUR = 24;      // midnight
const WINDOW_HOURS = WINDOW_END_HOUR - WINDOW_START_HOUR; // 16
const TIMELINE_HEIGHT = WINDOW_HOURS * HOUR_PX;            // 640
const HOUR_LABEL_WIDTH = 50;
const DAY_COL_WIDTH_PER_TRACK = 140;
const MIN_BLOCK_HEIGHT = 18;
const TRACK_GAP_PX = 2;

export function createTimelineView({ container, onEventClick }) {
  container.innerHTML = '';
  return {
    // allGroups: every group from the dataset (used to enumerate days).
    // savedIds, purchasedIds: Set<gencon_id>.
    // conflictedSessionIds: Set<gencon_id> | null — sessions that get a red
    //   outline + "!" badge. Computed by callers from groupOverlapMap.
    // previewGroup: a single group whose sessions render as preview blocks
    //   (overrides saved/purchased for those sessions). null when no detail panel open.
    render(allGroups, savedIds, purchasedIds, conflictedSessionIds, previewGroup, visibleCollections) {
      const days = collectDays(allGroups);
      const sessionsByDay = bucketSessions(
        allGroups, days, savedIds, purchasedIds, previewGroup, visibleCollections,
      );

      container.innerHTML = '';
      const root = document.createElement('div');
      root.className = 'tl-root';
      root.appendChild(renderHourRail());
      for (const day of days) {
        root.appendChild(renderDayColumn(
          day, sessionsByDay.get(day) || [], conflictedSessionIds, onEventClick, visibleCollections,
        ));
      }
      container.appendChild(root);
    },
  };
}

// GenCon 2026 official days: Thu 2026-07-30 through Sun 2026-08-02.
// Some sessions in the dataset start on pre-con setup days (e.g. Wed 7/29)
// or post-con (e.g. exhibitor breakdown Fri 8/7); those are out-of-scope
// for the timeline view, so we intersect any data-present day against this
// window before rendering columns.
const CON_DAYS = new Set([
  '2026-07-30', '2026-07-31', '2026-08-01', '2026-08-02',
]);

export function collectDays(allGroups) {
  const dayKeys = new Set();
  for (const g of allGroups) {
    for (const s of g.sessions || []) {
      if (!s.start) continue;
      const k = String(s.start).slice(0, 10);
      if (CON_DAYS.has(k)) dayKeys.add(k);
    }
  }
  return [...dayKeys].sort();
}

function bucketSessions(allGroups, days, savedIds, purchasedIds, previewGroup, visibleCollections) {
  const out = new Map();
  for (const day of days) out.set(day, []);
  // Build a union of all gencon_ids that any visible collection has flagged.
  const friendSessionIds = new Set();
  for (const c of (visibleCollections || [])) {
    for (const sid of c.saved || []) friendSessionIds.add(sid);
    for (const sid of c.purchased || []) friendSessionIds.add(sid);
  }
  for (const g of allGroups) {
    for (const s of g.sessions || []) {
      if (!s.start || !s.end || !s.gencon_id) continue;
      const day = String(s.start).slice(0, 10);
      if (!out.has(day)) continue;
      let kind = null;
      if (previewGroup && g.key === previewGroup.key) kind = 'preview';
      else if (purchasedIds.has(s.gencon_id)) kind = 'purchased';
      else if (savedIds.has(s.gencon_id)) kind = 'saved';
      else if (friendSessionIds.has(s.gencon_id)) kind = 'friend';
      if (!kind) continue;
      out.get(day).push({ ...s, _group: g, _kind: kind });
    }
  }
  return out;
}

function renderHourRail() {
  const rail = document.createElement('div');
  rail.className = 'tl-hour-rail';
  rail.style.width = HOUR_LABEL_WIDTH + 'px';
  const header = document.createElement('div');
  header.className = 'tl-hour-header';
  rail.appendChild(header);
  const body = document.createElement('div');
  body.className = 'tl-hour-body';
  body.style.height = TIMELINE_HEIGHT + 'px';
  for (let h = WINDOW_START_HOUR; h < WINDOW_END_HOUR; h++) {
    const lbl = document.createElement('div');
    lbl.className = 'tl-hour-label';
    lbl.style.height = HOUR_PX + 'px';
    lbl.textContent = formatHourLabel(h);
    body.appendChild(lbl);
  }
  rail.appendChild(body);
  return rail;
}

function renderDayColumn(day, daySessions, conflictedSessionIds, onEventClick, visibleCollections) {
  const sorted = [...daySessions].sort((a, b) =>
    a.start < b.start ? -1 : a.start > b.start ? 1 : 0,
  );
  const tracks = assignTracks(sorted);
  const trackCount = Math.max(1, ...[...tracks.values()].map(t => t + 1));
  const colWidth = trackCount * DAY_COL_WIDTH_PER_TRACK;

  const col = document.createElement('div');
  col.className = 'tl-day';
  col.style.width = colWidth + 'px';

  const header = document.createElement('div');
  header.className = 'tl-day-header';
  header.textContent = formatDayLabel(day);
  col.appendChild(header);

  const body = document.createElement('div');
  body.className = 'tl-day-body';
  body.style.height = TIMELINE_HEIGHT + 'px';
  body.style.position = 'relative';
  col.appendChild(body);

  for (const s of sorted) {
    body.appendChild(renderEvent(
      s, tracks.get(s.gencon_id), trackCount, conflictedSessionIds, onEventClick, visibleCollections,
    ));
  }
  return col;
}

function renderEvent(s, trackIdx, trackCount, conflictedSessionIds, onEventClick, visibleCollections) {
  const startMin = isoToMinutesOfDay(s.start);
  const endMin = isoToMinutesOfDay(s.end);
  const winStart = WINDOW_START_HOUR * 60;
  const winEnd = WINDOW_END_HOUR * 60;
  // For sessions that bleed past midnight (end on the next day), endMin can be
  // less than startMin — treat as winEnd (clipped at the bottom edge).
  const endClamped = endMin < startMin ? winEnd : endMin;
  const top = Math.max(0, (startMin - winStart) / 60 * HOUR_PX);
  const bottom = Math.min(TIMELINE_HEIGHT, (endClamped - winStart) / 60 * HOUR_PX);
  const height = Math.max(MIN_BLOCK_HEIGHT, bottom - top);
  const widthPct = 100 / trackCount;
  const leftPct = (trackIdx / trackCount) * 100;
  const conflict = conflictedSessionIds && conflictedSessionIds.has(s.gencon_id);

  const el = document.createElement('div');
  el.className = `tl-event tl-${s._kind}${conflict ? ' tl-conflict' : ''}`;
  el.style.top = top + 'px';
  el.style.height = height + 'px';
  el.style.left = `calc(${leftPct}% + ${trackIdx === 0 ? 0 : TRACK_GAP_PX}px)`;
  el.style.width = `calc(${widthPct}% - ${TRACK_GAP_PX}px)`;
  el.dataset.sessionId = s.gencon_id;

  const beforeWindow = startMin < winStart;
  const afterWindow = endMin > winEnd || endMin < startMin;

  el.innerHTML = `
    ${conflict ? '<span class="tl-badge">!</span>' : ''}
    ${beforeWindow ? '<span class="tl-out before">←</span>' : ''}
    <div class="tl-title">${escape(s._group.title || '')}</div>
    <div class="tl-meta">${formatTime(startMin)}–${formatTime(endMin)}${s.location ? ' · ' + escape(s.location) : ''}</div>
    ${afterWindow ? '<span class="tl-out after">→</span>' : ''}
  `;
  // Append per-collection dots for collections that flagged this session.
  const matches = (visibleCollections || []).filter(c =>
    (c.saved || []).includes(s.gencon_id) || (c.purchased || []).includes(s.gencon_id)
  );
  if (matches.length > 0) {
    const dotsEl = document.createElement('span');
    dotsEl.className = 'tl-dots';
    const shown = matches.slice(0, 4);
    const extra = matches.length - shown.length;
    for (const c of shown) {
      const d = document.createElement('span');
      d.className = 'friend-dot';
      d.setAttribute('style', 'background:' + c.color);
      d.title = c.name;
      dotsEl.appendChild(d);
    }
    if (extra > 0) {
      const more = document.createElement('span');
      more.className = 'friend-dot-more';
      more.textContent = `+${extra}`;
      dotsEl.appendChild(more);
    }
    el.appendChild(dotsEl);
  }

  el.addEventListener('click', () => onEventClick && onEventClick(s._group, s));
  return el;
}

function isoToMinutesOfDay(iso) {
  const m = String(iso).match(/T(\d{2}):(\d{2})/);
  if (!m) return 0;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function formatHourLabel(h) {
  if (h === 0) return '12a';
  if (h < 12) return `${h}a`;
  if (h === 12) return '12p';
  return `${h - 12}p`;
}

function formatTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const ampm = h < 12 ? 'a' : 'p';
  const h12 = ((h + 11) % 12) + 1;
  return m === 0 ? `${h12}${ampm}` : `${h12}:${String(m).padStart(2, '0')}${ampm}`;
}

function formatDayLabel(isoDay) {
  const d = new Date(isoDay + 'T12:00:00');
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()] +
    ` ${d.getMonth() + 1}/${d.getDate()}`;
}

function escape(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
