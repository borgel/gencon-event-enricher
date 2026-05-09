// Build deep-link URLs for sources. BGG is fully verified; GenCon is best-effort.

export function bggUrl(bggId) {
  if (bggId == null) return null;
  return `https://boardgamegeek.com/boardgame/${bggId}`;
}

// GenCon's per-event page is at /events/<numeric-id>. The alphanumeric
// gencon_id is "<EVENTTYPE>26ND<numeric>" (e.g. BGM26ND313243 → /events/313243).
// Fall back to the event-finder search if the ID doesn't parse.
export function genconUrl(gameId) {
  if (!gameId) return null;
  const m = String(gameId).match(/(\d+)$/);
  if (m) return `https://www.gencon.com/events/${m[1]}`;
  return `https://www.gencon.com/events?search=${encodeURIComponent(gameId)}`;
}
