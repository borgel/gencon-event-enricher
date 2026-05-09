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

// Build a Google Calendar "create event" URL prefilled with title, time,
// description and location. Times in the dataset are naive Indianapolis
// wall-clock; the `ctz` parameter tells Google to interpret them in that
// zone and display in the viewing user's local time.
const GENCON_TZ = 'America/Indiana/Indianapolis';

export function googleCalendarUrl(group, session) {
  if (!group || !session?.start) return null;
  const startWall = formatGcal(session.start);
  const endWall = formatGcal(session.end || addMinutes(session.start, group.duration_minutes ?? 60));
  if (!startWall || !endWall) return null;

  const text = `${group.title}${session.gencon_id ? ` (${session.gencon_id})` : ''}`;
  const eventUrl = genconUrl(session.gencon_id);
  const description = group.long_description || group.short_description || '';
  const details = eventUrl ? `${description}\n\n${eventUrl}` : description;
  const location = [
    session.location,
    session.room,
    session.table ? `Table ${session.table}` : null,
  ].filter(Boolean).join(' · ');

  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text,
    dates: `${startWall}/${endWall}`,
    details,
    location,
    ctz: GENCON_TZ,
  });
  return `https://www.google.com/calendar/event?${params.toString()}`;
}

// '2026-07-30T09:00:00' -> '20260730T090000'
function formatGcal(iso) {
  if (!iso) return null;
  return String(iso).replace(/[-:]/g, '').replace(/\.\d+/, '');
}

function addMinutes(iso, minutes) {
  if (!iso) return null;
  // Treat ISO as wall time (no timezone parsing) so we don't shift across
  // DST boundaries; arithmetic is on a Date but the input/output are both
  // local-wall in the same nominal zone.
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() + (minutes || 60));
  // Re-emit in the same naive ISO shape (no Z, no offset).
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
