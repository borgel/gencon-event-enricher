// Pure functions for overlap detection and lane packing.
// All inputs are session-shaped objects: { gencon_id, start, end, ... }.
// `start` and `end` are naive ISO strings (Indianapolis local wall time).

// Returns a Set of gencon_id values for sessions whose [start, end) interval
// overlaps another session in the same input array on the same calendar day.
// Closed-open intervals: A 9–10 and B 10–11 do NOT overlap.
export function detectOverlaps(sessions) {
  const out = new Set();
  // Bucket by date prefix (YYYY-MM-DD).
  const byDay = new Map();
  for (const s of sessions) {
    if (!s?.start || !s?.end || !s?.gencon_id) continue;
    const day = String(s.start).slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(s);
  }
  for (const list of byDay.values()) {
    list.sort((a, b) => a.start < b.start ? -1 : a.start > b.start ? 1 : 0);
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        if (list[j].start >= list[i].end) break; // sorted; no further overlaps
        // Overlap (start of j is before end of i, and j.start >= i.start by sort).
        out.add(list[i].gencon_id);
        out.add(list[j].gencon_id);
      }
    }
  }
  return out;
}

// Greedy lane-pack on a single-day session list. Returns Map<gencon_id, trackIndex>.
// Sort by start; assign each session to the lowest-numbered track whose last-end
// is <= session.start.
export function assignTracks(sessions) {
  const sorted = [...sessions].sort((a, b) =>
    a.start < b.start ? -1 : a.start > b.start ? 1 : 0
  );
  const trackEnds = []; // trackEnds[i] = ISO end-time of the latest session in track i
  const out = new Map();
  for (const s of sorted) {
    let placed = -1;
    for (let i = 0; i < trackEnds.length; i++) {
      if (trackEnds[i] <= s.start) {
        placed = i;
        break;
      }
    }
    if (placed === -1) {
      placed = trackEnds.length;
      trackEnds.push(s.end);
    } else {
      trackEnds[placed] = s.end;
    }
    out.set(s.gencon_id, placed);
  }
  return out;
}

// Inspect every saved/purchased session across all groups, and report:
//   conflictedGroups: Set<groupKey>   — groups with at least one saved/purchased
//                                       session that overlaps another claimed
//                                       session (potentially in a different group)
//   perSession: Map<gencon_id, { fits: bool, conflictsWith: [{groupKey, title, sessionId}] }>
//                                     — for each claimed session, whether it
//                                       fits and what it conflicts with
//
// "Claimed" = saved OR purchased. The two sets are unioned for overlap purposes
// (a purchased session conflicts with a saved one, etc.).
export function groupOverlapMap(groups, savedIds, purchasedIds) {
  const claimed = []; // [{ gencon_id, groupKey, title, start, end }]
  for (const g of groups) {
    for (const s of g.sessions || []) {
      if (!s.gencon_id || !s.start || !s.end) continue;
      if (!savedIds.has(s.gencon_id) && !purchasedIds.has(s.gencon_id)) continue;
      claimed.push({
        gencon_id: s.gencon_id,
        groupKey: g.key,
        title: g.title || '',
        start: s.start,
        end: s.end,
      });
    }
  }

  const perSession = new Map();
  for (const c of claimed) {
    perSession.set(c.gencon_id, { fits: true, conflictsWith: [] });
  }

  const byDay = new Map();
  for (const c of claimed) {
    const day = String(c.start).slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(c);
  }

  for (const list of byDay.values()) {
    list.sort((a, b) => a.start < b.start ? -1 : a.start > b.start ? 1 : 0);
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        if (list[j].start >= list[i].end) break;
        const a = list[i], b = list[j];
        perSession.get(a.gencon_id).fits = false;
        perSession.get(a.gencon_id).conflictsWith.push({
          groupKey: b.groupKey, title: b.title, sessionId: b.gencon_id,
        });
        perSession.get(b.gencon_id).fits = false;
        perSession.get(b.gencon_id).conflictsWith.push({
          groupKey: a.groupKey, title: a.title, sessionId: a.gencon_id,
        });
      }
    }
  }

  const conflictedGroups = new Set();
  for (const c of claimed) {
    const info = perSession.get(c.gencon_id);
    if (info && !info.fits) conflictedGroups.add(c.groupKey);
  }

  return { conflictedGroups, perSession };
}
