// Repo Radio — Seasons library view.
// Groups REAL aired episodes by category (tags on their web/memory.json
// observation, keyed by episode_id) into compact season sections inside the
// existing #episode-list sidebar container, plus a hand-authored "up next
// this season" queue (web/seasons.json, derived from pipeline/watchlist.json).
// NEVER renders fake episodes — only real ep-*.json entries + clearly-marked
// QUEUED watchlist repos.
//
// Owns: this file + web/seasons.json. Renders entirely inside #episode-list;
// no index.html markup depended on beyond that container existing.

const CATEGORY_LABELS = {
  "agent-framework": "Agent Frameworks",
  "dev-tool": "Dev Tools",
  "ai-app": "AI Apps",
  "memory": "Memory",
};

function titleCase(s) {
  return s.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function seasonLabel(category) {
  if (!category) return "SEASON 1";
  const name = CATEGORY_LABELS[category] || titleCase(category);
  return `${name.toUpperCase()} — SEASON 1`;
}

function avatarUrl(fullName) {
  const owner = (fullName || "").split("/")[0];
  return owner ? `https://github.com/${owner}.png?size=64` : "";
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── Data loading (defensive: missing/malformed files degrade to empty, never throw) ──
export async function loadSeasonsData(cfg) {
  const base = cfg?.STATIC_BASE || "";
  const tagsByEpisode = {};
  try {
    const r = await fetch(`${base}/memory.json`, { cache: "no-store" });
    if (r.ok) {
      const data = await r.json();
      const entries = Array.isArray(data) ? data : (data && (data.entries || data.observations)) || [];
      entries.forEach((e) => {
        if (e && e.episode_id && Array.isArray(e.tags) && e.tags.length) {
          tagsByEpisode[e.episode_id] = e.tags;
        }
      });
    }
  } catch {}

  let queuedSeasons = [];
  try {
    const r = await fetch(`${base}/seasons.json`, { cache: "no-store" });
    if (r.ok) {
      const data = await r.json();
      if (Array.isArray(data?.seasons)) queuedSeasons = data.seasons;
    }
  } catch {}

  return { tagsByEpisode, queuedSeasons };
}

// category(ep): first tag on its memory.json observation is treated as the
// primary/season-defining category; episodes with no tagged observation fall
// back to a shared untitled "Season 1" bucket (never invented).
function categoryFor(ep, tagsByEpisode) {
  const tags = tagsByEpisode[ep.id];
  return (tags && tags[0]) || null;
}

function episodeRow(ep, active, onSelect) {
  const row = document.createElement("button");
  row.className =
    "w-full text-left px-4 py-2.5 flex items-center gap-2.5 hover:bg-white/[.02] transition-colors" +
    (active ? " bg-white/[.03]" : "");
  row.style.borderTop = "1px solid var(--border)";
  const av = avatarUrl(ep.repo?.full_name);
  row.innerHTML = `
    ${av ? `<img src="${av}" alt="" width="20" height="20" class="rounded-full shrink-0" style="border:1px solid var(--border)" loading="lazy">` : ""}
    <span class="font-mono2 text-[10px] shrink-0" style="color: var(--amber-dim)">${ep.id.replace("ep-", "EP")}</span>
    <span class="flex-1 min-w-0">
      <span class="block text-[12.5px] truncate" style="color: var(--text)">${escHtml(ep.repo?.full_name || "")}</span>
      <span class="block font-mono2 text-[9.5px] truncate" style="color: var(--text-2)">${escHtml(ep.title || "")}</span>
    </span>
    <span class="w-2 h-2 rounded-full vdot-${ep.verdict} shrink-0" title="${ep.verdict || ""}"></span>
    ${active ? '<span class="eq paused" id="eq-now"><span></span><span></span><span></span><span></span><span></span></span>' : ""}`;
  row.addEventListener("click", () => { if (!active) onSelect(ep.id); });
  return row;
}

function queuedRow(repo) {
  const row = document.createElement("div");
  row.className = "px-4 py-2 flex items-center gap-2.5 opacity-70";
  row.style.borderTop = "1px solid var(--border)";
  const av = avatarUrl(repo.full_name);
  const stars = Number(repo.stars || 0).toLocaleString();
  const vel = Number(repo.velocity_per_hr || 0);
  row.innerHTML = `
    ${av ? `<img src="${av}" alt="" width="18" height="18" class="rounded-full shrink-0" style="border:1px solid var(--border)" loading="lazy">` : ""}
    <span class="flex-1 min-w-0 text-[11.5px] truncate" style="color: var(--text-2)">${escHtml(repo.full_name || "")}</span>
    <span class="font-mono2 text-[9.5px] shrink-0" style="color: var(--text-2)">★${stars}</span>
    <span class="font-mono2 text-[9.5px] shrink-0" style="color: var(--amber-dim)">+${vel}/hr</span>
    <span class="font-mono2 text-[8.5px] shrink-0 px-1.5 py-0.5 rounded" style="color: var(--teal); border: 1px solid rgba(94,234,212,.35)">QUEUED</span>`;
  return row;
}

// Preserves collapse state across re-renders (module-level, session-scoped).
const collapsed = new Map(); // category-key -> bool

export function renderSeasonList({ container, episodes, activeId, tagsByEpisode, queuedSeasons, onSelect }) {
  container.innerHTML = "";

  // Group real episodes by category.
  const byCategory = new Map(); // key -> { label, episodes: [] }
  episodes.forEach((ep) => {
    const cat = categoryFor(ep, tagsByEpisode);
    const key = cat || "__untagged";
    if (!byCategory.has(key)) byCategory.set(key, { category: cat, episodes: [] });
    byCategory.get(key).episodes.push(ep);
  });

  // Merge in queued-only categories (seasons with no aired episode yet).
  (queuedSeasons || []).forEach((s) => {
    const key = s.category || "__untagged";
    if (!byCategory.has(key)) byCategory.set(key, { category: s.category, episodes: [] });
  });

  if (!byCategory.size) return; // nothing real to show — leave container empty

  const activeCategoryKey = (() => {
    const ep = episodes.find((e) => e.id === activeId);
    if (!ep) return null;
    return categoryFor(ep, tagsByEpisode) || "__untagged";
  })();

  // Sort: category containing the active episode first, then by episode count desc, then name.
  const keys = [...byCategory.keys()].sort((a, b) => {
    if (a === activeCategoryKey) return -1;
    if (b === activeCategoryKey) return 1;
    return byCategory.get(b).episodes.length - byCategory.get(a).episodes.length;
  });

  keys.forEach((key) => {
    const group = byCategory.get(key);
    const queued = (queuedSeasons || []).find((s) => (s.category || "__untagged") === key)?.queued || [];
    if (!group.episodes.length && !queued.length) return;

    if (!collapsed.has(key)) collapsed.set(key, key !== activeCategoryKey);
    const isCollapsed = collapsed.get(key);

    const section = document.createElement("div");

    const header = document.createElement("button");
    header.className = "w-full text-left px-4 py-2 flex items-center gap-2 hover:bg-white/[.02]";
    header.style.borderTop = "1px solid var(--border)";
    header.innerHTML = `
      <span class="font-mono2 text-[9.5px] tracking-[0.15em]" style="color: var(--teal)">${seasonLabel(group.category)}</span>
      <span class="flex-1"></span>
      <span class="font-mono2 text-[9px]" style="color: var(--text-2)">${group.episodes.length ? `${group.episodes.length} ep` : ""}</span>
      <span class="font-mono2 text-[10px] transition-transform" style="color: var(--text-2); display:inline-block; transform: ${isCollapsed ? "" : "rotate(90deg)"}">&#9656;</span>`;
    section.appendChild(header);

    const body = document.createElement("div");
    body.classList.toggle("hidden", isCollapsed);

    [...group.episodes].reverse().forEach((ep) => {
      body.appendChild(episodeRow(ep, ep.id === activeId, onSelect));
    });

    if (queued.length) {
      const qlabel = document.createElement("div");
      qlabel.className = "px-4 pt-2 pb-1";
      qlabel.style.borderTop = group.episodes.length ? "1px solid var(--border)" : "";
      qlabel.innerHTML = `<span class="font-mono2 text-[8.5px] tracking-[0.15em]" style="color: var(--text-2)">UP NEXT THIS SEASON</span>`;
      body.appendChild(qlabel);
      queued.slice(0, 4).forEach((repo) => body.appendChild(queuedRow(repo)));
    }

    section.appendChild(body);

    header.addEventListener("click", () => {
      const next = !collapsed.get(key);
      collapsed.set(key, next);
      body.classList.toggle("hidden", next);
      header.querySelector("span:last-child").style.transform = next ? "" : "rotate(90deg)";
    });

    container.appendChild(section);
  });
}
