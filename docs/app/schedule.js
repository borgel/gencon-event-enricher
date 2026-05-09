// Export and import the user's saved/purchased schedule as CSV.
//
// Columns: event_id, gencon_id, title, when, saved, purchased
// - event_id is the numeric trailing digits of gencon_id (e.g. 313243).
//   It's the load-bearing matcher on import; gencon_id is a fallback.
// - title and when are informational so the CSV is readable in Excel.
// - Only sessions with saved=1 or purchased=1 are included on export.

export function exportSchedule(groups, saved, purchased) {
  const rows = [['event_id', 'gencon_id', 'title', 'when', 'saved', 'purchased']];
  for (const g of groups) {
    for (const s of g.sessions || []) {
      const isSaved = saved.has(s.gencon_id);
      const isPurch = purchased.has(s.gencon_id);
      if (!isSaved && !isPurch) continue;
      const m = String(s.gencon_id || '').match(/(\d+)$/);
      const numeric = m ? m[1] : '';
      rows.push([
        numeric,
        s.gencon_id || '',
        g.title || '',
        s.start || '',
        isSaved ? '1' : '0',
        isPurch ? '1' : '0',
      ]);
    }
  }
  return rows.map(r => r.map(csvEscape).join(',')).join('\n') + '\n';
}

export function parseScheduleCSV(text, groups) {
  const rows = parseCSV(text);
  if (rows.length < 2) {
    return { saved: new Set(), purchased: new Set(), matched: 0, missed: 0 };
  }
  const header = rows[0].map(h => h.trim().toLowerCase());
  const idx = {
    event_id: header.indexOf('event_id'),
    gencon_id: header.indexOf('gencon_id'),
    saved: header.indexOf('saved'),
    purchased: header.indexOf('purchased'),
  };

  // Build maps from the currently-loaded dataset for matching.
  const byNumeric = new Map();
  const allIds = new Set();
  for (const g of groups) {
    for (const s of g.sessions || []) {
      if (!s.gencon_id) continue;
      allIds.add(s.gencon_id);
      const m = String(s.gencon_id).match(/(\d+)$/);
      if (m) byNumeric.set(m[1], s.gencon_id);
    }
  }

  const newSaved = new Set();
  const newPurchased = new Set();
  let matched = 0, missed = 0;
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (r.length === 0 || (r.length === 1 && r[0] === '')) continue;
    let gid = null;
    if (idx.event_id >= 0 && r[idx.event_id]) {
      gid = byNumeric.get(r[idx.event_id].trim()) || null;
    }
    if (!gid && idx.gencon_id >= 0 && r[idx.gencon_id]) {
      const candidate = r[idx.gencon_id].trim();
      if (allIds.has(candidate)) gid = candidate;
    }
    if (!gid) { missed++; continue; }
    matched++;
    if (idx.saved >= 0 && truthy(r[idx.saved])) newSaved.add(gid);
    if (idx.purchased >= 0 && truthy(r[idx.purchased])) newPurchased.add(gid);
  }
  return { saved: newSaved, purchased: newPurchased, matched, missed };
}

export function triggerDownload(filename, content, mime = 'text/csv') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function truthy(v) {
  return /^(1|true|yes)$/i.test(String(v ?? '').trim());
}

function csvEscape(v) {
  const s = String(v ?? '');
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

// Minimal RFC4180-ish CSV parser. Handles quoted fields with embedded
// commas, doubled-quote escapes, and CRLF or LF line endings.
function parseCSV(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else cell += c;
    } else {
      if (c === '"') inQuotes = true;
      else if (c === ',') { row.push(cell); cell = ''; }
      else if (c === '\n' || c === '\r') {
        if (cell !== '' || row.length > 0) { row.push(cell); rows.push(row); }
        row = []; cell = '';
        if (c === '\r' && text[i + 1] === '\n') i++;
      } else cell += c;
    }
  }
  if (cell !== '' || row.length > 0) { row.push(cell); rows.push(row); }
  return rows;
}
