import { bggUrl, genconUrl } from './links.js';
import { isSaved, toggleSaved } from './saved.js';

export function createDetailView({ panel, shell, onCloseToggle }) {
  panel.innerHTML = '';

  function close() {
    panel.classList.add('hidden');
    panel.setAttribute('aria-hidden', 'true');
    shell.classList.remove('detail-open');
    onCloseToggle && onCloseToggle();
  }
  function open() {
    panel.classList.remove('hidden');
    panel.setAttribute('aria-hidden', 'false');
    shell.classList.add('detail-open');
  }

  return {
    show(group) {
      panel.innerHTML = render(group);
      panel.querySelector('.close').addEventListener('click', close);
      const star = panel.querySelector('.save-toggle');
      star.addEventListener('click', () => {
        toggleSaved(group.key);
        star.classList.toggle('starred');
        star.textContent = isSaved(group.key) ? '★ Saved' : '☆ Save';
      });
      open();
    },
    hide: close,
  };
}

function render(g) {
  const saved = isSaved(g.key);
  return `
    <span class="close" title="Close detail">✕</span>
    <h2>${escape(g.title)}</h2>
    <div class="meta">${escape(g.event_type_label)} · ${formatPlayers(g)} · ${formatCost(g)} · ${escape(g.age_required)} · ${escape(g.experience_required)}</div>
    <div style="margin: 6px 0;">
      <button class="save-toggle ${saved ? 'starred' : ''}">${saved ? '★ Saved' : '☆ Save'}</button>
    </div>
    ${g.bgg ? bggCard(g.bgg) : '<div class="meta" style="font-style:italic">No BGG match.</div>'}
    <h3 style="margin-top:14px;font-size:14px">Description</h3>
    <p>${escape(g.long_description || g.short_description)}</p>
    <h3 style="margin-top:14px;font-size:14px">Sessions (${g.sessions.length})</h3>
    <table class="sessions">
      <thead><tr><th>When</th><th>Where</th><th>GM</th><th>Tix</th><th>Round</th><th></th></tr></thead>
      <tbody>${g.sessions.map(sessionRow).join('')}</tbody>
    </table>
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

function sessionRow(s) {
  const start = new Date(s.start);
  const end = s.end ? new Date(s.end) : null;
  return `
    <tr>
      <td>${formatDay(start)} ${formatTime(start)}${end ? '–' + formatTime(end) : ''}</td>
      <td>${escape(s.location || '')}${s.room ? ' · ' + escape(s.room) : ''}${s.table ? ' · t' + escape(s.table) : ''}</td>
      <td>${escape(s.gm || '')}</td>
      <td>${s.tickets_available ?? '—'}</td>
      <td>${s.total_rounds && s.total_rounds > 1 ? (s.round_number || '?') + '/' + s.total_rounds : ''}</td>
      <td><a href="${genconUrl(s.gencon_id)}" target="_blank" rel="noopener">↗</a></td>
    </tr>
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
