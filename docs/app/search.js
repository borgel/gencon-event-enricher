// MiniSearch wrapper. Index built lazily once on data load. Search returns
// a Set of matching keys.

const SEARCH_FIELDS = ['title', 'short_description', 'long_description', 'game_system'];

export function buildIndex(groups) {
  // MiniSearch is exposed as window.MiniSearch via the UMD bundle.
  const ms = new window.MiniSearch({
    fields: SEARCH_FIELDS,
    storeFields: ['key'],
    idField: 'key',
    searchOptions: { boost: { title: 3, game_system: 2 }, prefix: true, fuzzy: 0.1 },
  });
  ms.addAll(groups);
  return ms;
}

export function searchKeys(index, query) {
  if (!query || !query.trim()) return null;
  const hits = index.search(query.trim());
  return new Set(hits.map((h) => h.key));
}
