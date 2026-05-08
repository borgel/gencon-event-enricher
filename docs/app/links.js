// Build deep-link URLs for sources. BGG is fully verified; GenCon is best-effort.

export function bggUrl(bggId) {
  if (bggId == null) return null;
  return `https://boardgamegeek.com/boardgame/${bggId}`;
}

// GenCon's event finder accepts a search query. The Game ID search reliably
// surfaces a single event. If GenCon ships a more direct deep-link in the
// future, swap it in here.
export function genconUrl(gameId) {
  if (!gameId) return null;
  const q = encodeURIComponent(gameId);
  return `https://www.gencon.com/events?search=${q}`;
}
