// Loads and parses events.json. No transforms — webpage uses the JSON shape directly.
export async function loadData(url = 'data/events.json') {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to fetch ${url}: ${res.status}`);
  const blob = await res.json();
  if (!Array.isArray(blob.groups)) throw new Error('events.json: missing groups array');
  return blob;
}
