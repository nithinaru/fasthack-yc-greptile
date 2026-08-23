// Repo panel — owner avatar, full_name, description, language dot, stars, velocity,
// "View on GitHub ↗" link. Renders from the episode JSON's `repo` object (PRD §5/§4).
//
// This file cannot rely on app.js (owned by another agent) to call us directly, so it
// self-mounts: injects its own card markup next to the hero player, then watches
// #ep-title for text changes (app.js sets ep.title there on every loadEpisode()) to
// know when to re-render. We prefer window.RR_STATE?.episode if some other script ever
// sets it; otherwise we resolve the current episode id from #ep-date ("EP-00X · date")
// and fetch that episode's JSON ourselves, using the same STATIC_BASE convention as
// app.js (window.RR_CONFIG.STATIC_BASE + "/episodes/<id>.json").

const LANG_COLORS = {
  Python: "#3572A5",
  TypeScript: "#3178c6",
  JavaScript: "#f1e05a",
  Go: "#00ADD8",
  Rust: "#dea584",
};
const LANG_DEFAULT = "#8B8B9E";

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function fmtInt(n) {
  return Number(n || 0).toLocaleString();
}

function fmtVelocity(n) {
  const v = Number(n || 0);
  // Keep one decimal only when it's meaningfully fractional (e.g. 8.7), else integer.
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function ownerLogin(fullName) {
  if (!fullName || typeof fullName !== "string") return null;
  const i = fullName.indexOf("/");
  return i > 0 ? fullName.slice(0, i) : fullName;
}

// ── Mount point: a card in the hero column, right under the player/sync panel ──
function ensureMount() {
  let el = document.getElementById("repo-panel");
  if (el) return el;

  const host =
    document.querySelector("main .lg\\:col-span-8") || // hero section
    document.querySelector("main") ||
    document.body;

  el = document.createElement("div");
  el.id = "repo-panel";
  el.className = "card overflow-hidden mt-6 hidden"; // hidden until first render
  el.innerHTML = `
    <div class="px-4 py-2.5 border-b flex items-center gap-2" style="border-color: var(--border)">
      <span class="font-mono2 text-[10px] tracking-[0.2em]" style="color: var(--teal)">REPOSITORY</span>
    </div>
    <div class="p-4 flex items-start gap-4">
      <img id="rp-avatar" alt="" width="48" height="48"
           class="rounded-lg shrink-0" style="background: var(--bg); border: 1px solid var(--border)">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <a id="rp-fullname" href="#" target="_blank" rel="noopener"
             class="font-mono2 text-[14px] hover:underline" style="color: var(--text)">—/—</a>
          <span id="rp-lang" class="hidden items-center gap-1.5 font-mono2 text-[11px]" style="color: var(--text-2)">
            <span id="rp-lang-dot" class="w-2 h-2 rounded-full inline-block"></span>
            <span id="rp-lang-name"></span>
          </span>
        </div>
        <p id="rp-desc" class="hidden mt-1.5 text-[13px] leading-snug" style="color: var(--text-2)"></p>
        <div class="mt-2 flex items-center gap-4 flex-wrap">
          <span class="font-mono2 text-[12px]" style="color: var(--text-2)">
            ★ <span id="rp-stars" style="color: var(--text)">0</span>
          </span>
          <span id="rp-velocity" class="hidden font-mono2 text-[12px]" style="color: var(--amber)"></span>
          <a id="rp-link" href="#" target="_blank" rel="noopener"
             class="font-mono2 text-[12px] ml-auto hover:underline" style="color: var(--amber)">View on GitHub ↗</a>
        </div>
      </div>
    </div>`;

  // Place right after the sync panel grid (transcript/code), inside the hero column,
  // without touching any existing ids/sections.
  const syncGrid = host.querySelector(".grid.grid-cols-1.md\\:grid-cols-2");
  if (syncGrid && syncGrid.parentElement === host) {
    syncGrid.after(el);
  } else {
    host.appendChild(el);
  }
  return el;
}

function render(episode) {
  const repo = episode && episode.repo;
  if (!repo || !repo.full_name) return;

  const panel = ensureMount();
  panel.classList.remove("hidden");

  const owner = ownerLogin(repo.full_name);
  const avatar = panel.querySelector("#rp-avatar");
  if (owner) {
    avatar.src = `https://github.com/${owner}.png?size=96`;
    avatar.alt = owner;
  } else {
    avatar.removeAttribute("src");
  }

  const fullNameEl = panel.querySelector("#rp-fullname");
  fullNameEl.textContent = repo.full_name;
  fullNameEl.href = repo.url || "#";

  const descEl = panel.querySelector("#rp-desc");
  if (repo.description) {
    descEl.textContent = repo.description;
    descEl.classList.remove("hidden");
  } else {
    descEl.classList.add("hidden");
    descEl.textContent = "";
  }

  const langWrap = panel.querySelector("#rp-lang");
  if (repo.language) {
    panel.querySelector("#rp-lang-dot").style.background = LANG_COLORS[repo.language] || LANG_DEFAULT;
    panel.querySelector("#rp-lang-name").textContent = repo.language;
    langWrap.classList.remove("hidden");
    langWrap.classList.add("inline-flex");
  } else {
    langWrap.classList.add("hidden");
  }

  panel.querySelector("#rp-stars").textContent = fmtInt(repo.stars_at_airtime);

  const velEl = panel.querySelector("#rp-velocity");
  if (repo.velocity_per_hr != null) {
    velEl.textContent = `+${fmtVelocity(repo.velocity_per_hr)}/hr`;
    velEl.classList.remove("hidden");
  } else {
    velEl.classList.add("hidden");
  }

  const linkEl = panel.querySelector("#rp-link");
  linkEl.href = repo.url || "#";
}

// ── Episode resolution when we weren't handed one directly ──
function currentEpisodeIdFromDom() {
  // #ep-date text is "EP-00X · date" per app.js renderHero().
  const txt = document.getElementById("ep-date")?.textContent || "";
  const m = txt.match(/EP-(\d+)/i);
  if (!m) return null;
  return `ep-${m[1].padStart(3, "0")}`;
}

function staticUrl(path) {
  const base = (window.RR_CONFIG && window.RR_CONFIG.STATIC_BASE) || "";
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path;
  return `${base}${path}`;
}

let lastFetchedId = null;
async function fetchAndRenderById(id) {
  if (!id || id === lastFetchedId) return;
  lastFetchedId = id;
  try {
    const r = await fetch(staticUrl(`/episodes/${id}.json`), { cache: "no-store" });
    if (!r.ok) return;
    const ep = await r.json();
    render(ep);
  } catch {
    // defensive: leave panel as-is on fetch failure
  }
}

window.RR_renderRepoPanel = function RR_renderRepoPanel(episode) {
  if (!episode) return;
  lastFetchedId = episode.id || lastFetchedId;
  // Keep a global handle to the current episode so other same-owner modules (sync.js)
  // can resolve repo info (e.g. for GitHub deep links) without a second fetch.
  window.RR_STATE = window.RR_STATE || {};
  window.RR_STATE.episode = episode;
  render(episode);
};

function tryRenderFromState() {
  const ep = window.RR_STATE && window.RR_STATE.episode;
  if (ep && ep.repo) {
    window.RR_renderRepoPanel(ep);
    return true;
  }
  return false;
}

function reactToEpisodeChange() {
  if (tryRenderFromState()) return;
  const id = currentEpisodeIdFromDom();
  if (id) fetchAndRenderById(id);
}

function init() {
  ensureMount();

  // Some future app.js may dispatch this — listen defensively even though it doesn't today.
  window.addEventListener("rr:episode", (e) => {
    if (e.detail) window.RR_renderRepoPanel(e.detail);
  });

  // Primary mechanism per spec: observe #ep-title text changes (set on every loadEpisode()).
  const titleEl = document.getElementById("ep-title");
  if (titleEl) {
    const mo = new MutationObserver(() => reactToEpisodeChange());
    mo.observe(titleEl, { characterData: true, childList: true, subtree: true });
  }

  // Cover the initial render too (title mutation may fire before/without observer attach
  // depending on timing), plus a couple of short-delay retries for slow first boot.
  reactToEpisodeChange();
  setTimeout(reactToEpisodeChange, 300);
  setTimeout(reactToEpisodeChange, 1000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
