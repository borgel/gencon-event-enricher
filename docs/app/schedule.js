// Export and import the user's saved/purchased schedule as CSV.
//
// Columns: event_id, gencon_id, title, when, saved, purchased
// - event_id is the numeric trailing digits of gencon_id (e.g. 313243).
//   It's the load-bearing matcher on import; gencon_id is a fallback.
// - title and when are informational so the CSV is readable in Excel.
// - Only sessions with saved=1 or purchased=1 are included on export.
// - If options.name is a non-empty string, a leading '# name=<value>' row is
//   written before the column header. parseScheduleCSV reads it back out.

export function exportSchedule(groups, saved, purchased, options = {}) {
  const rows = [];
  if (options.name) {
    const safeName = String(options.name).replace(/[\r\n]+/g, ' ').trim();
    if (safeName) rows.push([`# name=${safeName}`]);
  }
  rows.push(['event_id', 'gencon_id', 'title', 'when', 'saved', 'purchased']);
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
  return rows.map(r => {
    // Metadata rows are written as a single literal cell with no escaping
    // (they start with '#', so CSV consumers ignore the line cleanly).
    if (r.length === 1 && r[0].startsWith('#')) return r[0];
    return r.map(csvEscape).join(',');
  }).join('\n') + '\n';
}

export function parseScheduleCSV(text, groups) {
  // Strip leading '#'-prefixed metadata lines BEFORE CSV tokenization so
  // metadata values containing commas don't get mis-tokenized as cells.
  const lines = text.split(/\r?\n/);
  let name = '';
  let dataStart = 0;
  while (dataStart < lines.length && lines[dataStart].startsWith('#')) {
    const meta = lines[dataStart].slice(1).trim();
    const eq = meta.indexOf('=');
    if (eq > 0) {
      const k = meta.slice(0, eq).trim();
      const v = meta.slice(eq + 1).trim();
      if (k === 'name') name = v;
      // unknown keys ignored
    }
    dataStart++;
  }
  const rows = parseCSV(lines.slice(dataStart).join('\n'));
  if (rows.length < 2) {
    return { name, saved: new Set(), purchased: new Set(), matched: 0, missed: 0 };
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
  for (let j = 1; j < rows.length; j++) {
    const r = rows[j];
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
  return { name, saved: newSaved, purchased: newPurchased, matched, missed };
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

// ─── Base64 blob codec ────────────────────────────────────────────────────
// Wire format: `GENCON1:<urlsafe-base64>` where the body is
// deflate-raw(utf8(csv)). The csv is the exact string exportSchedule(...)
// produces, so existing parsers (parseScheduleCSV) and matchers remain the
// single source of truth.

const BLOB_PREFIX = 'GENCON1:';
const BLOB_BODY_RE = /GENCON1:([A-Za-z0-9_-]+)/;

async function deflateRaw(bytes) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new CompressionStream('deflate-raw'));
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

async function inflateRaw(bytes) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream('deflate-raw'));
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

function b64urlEncode(bytes) {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlDecode(s) {
  const std = s.replace(/-/g, '+').replace(/_/g, '/');
  const padLen = (4 - (std.length % 4)) % 4;
  const bin = atob(std + '='.repeat(padLen));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

export async function encodeBlob(csv) {
  const utf8 = new TextEncoder().encode(csv);
  const deflated = await deflateRaw(utf8);
  return BLOB_PREFIX + b64urlEncode(deflated);
}

// Extracts the first GENCON1: token from `text` and decodes it. Returns the
// recovered CSV string on success, or null for any failure (missing prefix,
// base64 error, decompression error). Surrounding chat text is tolerated.
export async function decodeBlob(text) {
  const m = BLOB_BODY_RE.exec(text || '');
  if (!m) return null;
  try {
    const bytes = b64urlDecode(m[1]);
    const inflated = await inflateRaw(bytes);
    return new TextDecoder().decode(inflated);
  } catch {
    return null;
  }
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
