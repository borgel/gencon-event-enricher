import { bggUrl, genconUrl, googleCalendarUrl } from './links.js';
import { isSaved, toggleSaved, isPurchased, togglePurchased } from './saved.js';

export function createDetailView({ panel, onCloseToggle, onChange, onShow, onClose }) {
  panel.innerHTML = '';
  let currentOverlapInfo = null;

  function close() {
    panel.classList.add('hidden');
    panel.setAttribute('aria-hidden', 'true');
    onCloseToggle && onCloseToggle();
    onClose && onClose();
  }
  function open() {
    panel.classList.remove('hidden');
    panel.setAttribute('aria-hidden', 'false');
  }
  const fireChange = () => { onChange && onChange(); };

  return {
    show(group, overlapInfoMap, opts) {
      currentOverlapInfo = overlapInfoMap || null;
      panel.innerHTML = render(group, currentOverlapInfo, opts?.allCollections);
      panel.querySelector('.close').addEventListener('click', close);
      // Wire per-session toggles. Each .session-card carries its session id
      // in data-session-id; saved/purchased state is keyed on that.
      panel.querySelectorAll('.session-card').forEach((card) => {
        const sid = card.dataset.sessionId;
        if (!sid) return;
        const star = card.querySelector('.save-toggle');
        star?.addEventListener('click', () => {
          toggleSaved(sid);
          star.classList.toggle('starred');
          star.textContent = isSaved(sid) ? '★ Saved' : '☆ Save';
          fireChange();
        });
        const purchased = card.querySelector('.purchased-cb');
        purchased?.addEventListener('change', () => {
          togglePurchased(sid);
          fireChange();
        });
      });
      open();
      // opts.skipOnShow lets callers re-render the panel without re-firing
      // the onShow callback (used by applyFilters to refresh the panel in
      // place — otherwise onShow's applyFilters would recurse).
      if (!opts?.skipOnShow) onShow && onShow(group);
    },
    hide: close,
  };
}

function render(g, perSessionOverlap, allCollections) {
  return `
    <span class="close" title="Close detail">✕</span>
    <h2>${escape(g.title)}</h2>
    <div class="meta">${escape(g.event_type_label)} · ${formatPlayers(g)} · ${formatCost(g)} · ${escape(g.age_required)} · ${escape(g.experience_required)}</div>
    ${alsoSavedByHtml(g, allCollections)}
    ${signupRow(g)}
    ${g.bgg ? bggCard(g.bgg) : '<div class="meta" style="font-style:italic">No BGG match.</div>'}
    <h3 style="margin-top:14px;font-size:14px">Description</h3>
    <p>${escape(g.long_description || g.short_description)}</p>
    <h3 style="margin-top:14px;font-size:14px">Sessions (${g.sessions.length})</h3>
    ${g.sessions.map(s => sessionCard(s, g, perSessionOverlap?.get(s.gencon_id))).join('')}
  `;
}

function signupRow(g) {
  if (!g.sessions?.length) return '';
  const buttons = g.sessions.map(s => {
    const url = genconUrl(s.gencon_id);
    if (!url) return '';
    const start = new Date(s.start);
    const label = `${formatDay(start)} ${formatTime(start)}`;
    return `<a class="signup-btn" href="${url}" target="_blank" rel="noopener">${escape(label)} ↗</a>`;
  }).filter(Boolean).join('');
  if (!buttons) return '';
  return `
    <div class="signup-row">
      <span class="signup-label">Sign up:</span>
      ${buttons}
    </div>
  `;
}

function bggCard(bgg) {
  return `
    <div class="bgg-card">
      <div><strong><a href="${bggUrl(bgg.id)}" target="_blank" rel="noopener">${escape(bgg.name)}</a></strong>
        ${bgg.year_published ? ` · ${bgg.year_published}` : ''}
        ${bgg.is_expansion ? ' <span class="meta">(expansion)</span>' : ''}
      </div>
      <div class="meta">
        ★ Geek ${fmt(bgg.bayesaverage)} · Avg ${fmt(bgg.average)} · ${(bgg.users_rated || 0).toLocaleString()} ratings
        ${bgg.rank ? ` · #${bgg.rank} overall` : ''}
        ${categoryRank(bgg.category_ranks)}
      </div>
      <div class="meta">match: ${escape(bgg.match_source)}</div>
    </div>
  `;
}

function categoryRank(ranks) {
  if (!ranks) return '';
  const entry = Object.entries(ranks).sort((a, b) => a[1] - b[1])[0];
  if (!entry) return '';
  return ` · #${entry[1]} ${entry[0]}`;
}

function sessionCard(s, g, overlapInfo) {
  const start = new Date(s.start);
  const end = s.end ? new Date(s.end) : null;
  const saved = isSaved(s.gencon_id);
  const purchased = isPurchased(s.gencon_id);
  const cal = googleCalendarUrl(g, s);
  const where = [
    s.location, s.room, s.table ? `Table ${s.table}` : null,
  ].filter(Boolean).map(escape).join(' · ');
  const tix = s.tickets_available ?? '—';
  const round = s.total_rounds && s.total_rounds > 1
    ? ` · Round ${s.round_number || '?'}/${s.total_rounds}` : '';
  const fitText = overlapInfo && !overlapInfo.fits && overlapInfo.conflictsWith.length
    ? `⚠️ Conflicts with ${escape(overlapInfo.conflictsWith[0].title)}`
    : '✓ Fits your schedule';
  const fitClass = overlapInfo && !overlapInfo.fits ? 'session-fit conflict' : 'session-fit';
  return `
    <div class="session-card" data-session-id="${escape(s.gencon_id)}">
      <div class="session-when">${formatDay(start)} ${formatTime(start)}${end ? '–' + formatTime(end) : ''}</div>
      ${where ? `<div class="session-where">${where}</div>` : ''}
      <div class="session-meta">
        ${s.gm ? `GM: ${escape(s.gm)} · ` : ''}${tix} tickets${round}
      </div>
      <div class="${fitClass}">${fitText}</div>
      <div class="session-actions">
        <button class="save-toggle ${saved ? 'starred' : ''}">${saved ? '★ Saved' : '☆ Save'}</button>
        <label class="purchased-toggle">
          <input type="checkbox" class="purchased-cb"${purchased ? ' checked' : ''}>
          🎟️ Tickets purchased
        </label>
        <span class="session-links">
          <a href="${genconUrl(s.gencon_id)}" target="_blank" rel="noopener" title="Open on GenCon">↗</a>
          ${cal ? `<a href="${cal}" target="_blank" rel="noopener" title="Add to Google Calendar">📅</a>` : ''}
        </span>
      </div>
    </div>
  `;
}

function formatDay(d) {
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
}
function formatTime(d) {
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, '0');
  const ampm = h < 12 ? 'a' : 'p';
  return `${((h + 11) % 12) + 1}:${m}${ampm}`;
}
function formatPlayers(g) {
  if (g.min_players == null && g.max_players == null) return '';
  if (g.min_players === g.max_players) return `${g.min_players} players`;
  return `${g.min_players ?? '?'}–${g.max_players ?? '?'} players`;
}
function formatCost(g) {
  if (g.cost == null) return '';
  return g.cost === 0 ? 'free' : `$${g.cost.toFixed(2)}`;
}
function fmt(x) { return x == null ? '—' : x.toFixed(2); }
function escape(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function escapeAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function alsoSavedByHtml(g, allCollections) {
  const matches = (allCollections || []).filter(c =>
    g.sessions?.some(s => (c.saved || []).includes(s.gencon_id) || (c.purchased || []).includes(s.gencon_id))
  );
  if (matches.length === 0) return '';
  const chips = matches.map(c => `
    <span class="chip" data-id="${escapeAttr(c.id)}">
      <span class="swatch" style="background:${escapeAttr(c.color)}"></span>
      <span class="name">${escape(c.name)}</span>
    </span>
  `).join('');
  return `<div class="also-saved-by"><span class="label">Also saved by:</span>${chips}</div>`;
}
