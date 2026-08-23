// C3 — karaoke sync: transcript highlight/scroll + citation-driven code card.
const PAD = 0.5;               // segment window padding (s)
const SCROLL_SUPPRESS_MS = 3000; // pause auto-scroll after manual scroll

function fmtTs(t) {
  const m = Math.floor(t / 60), s = String(Math.floor(t % 60)).padStart(2, "0");
  return `${m}:${s}`;
}

function segRow(s, cls) {
  const row = document.createElement("div");
  row.className = cls;
  row.dataset.i = s.i;
  row.innerHTML = `<span class="ts">${fmtTs(s.start)}</span>${s.text}` +
    (s.citation ? `<span class="cite-chip">${s.citation.file}:${s.citation.start_line}</span>` : "");
  return row;
}

// Active segment for time t: prefer exact [start,end) containment, else ±PAD window.
function findActive(segments, t) {
  let padded = null;
  for (const s of segments) {
    if (s.start <= t && t < s.end) return s;
    if (padded === null && s.start - PAD <= t && t < s.end + PAD) padded = s;
  }
  return padded;
}

// Build the GitHub deep-link URL for a citation, given the episode's repo full_name
// and default_branch (falls back to "main" per PRD instructions).
function citationUrl(repoInfo, c) {
  if (!repoInfo?.full_name || !c) return null;
  const branch = repoInfo.default_branch || "main";
  return `https://github.com/${repoInfo.full_name}/blob/${branch}/${c.file}#L${c.start_line}-L${c.end_line}`;
}

// #ep-date text is "EP-00X · date" (app.js renderHero()) — used only as a last-resort
// way to identify the current episode when nobody handed us repo info directly.
function currentEpisodeIdFromDom() {
  const txt = document.getElementById("ep-date")?.textContent || "";
  const m = txt.match(/EP-(\d+)/i);
  return m ? `ep-${m[1].padStart(3, "0")}` : null;
}

function staticUrl(path) {
  const base = (window.RR_CONFIG && window.RR_CONFIG.STATIC_BASE) || "";
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path;
  return `${base}${path}`;
}

// Resolve {full_name, default_branch} for deep links. Prefers an explicitly passed
// `repo`, then window.RR_STATE.episode.repo (repopanel.js keeps this current), then
// falls back to fetching the episode JSON ourselves by id — self-contained per spec.
async function resolveRepoInfo(passedRepo) {
  if (passedRepo?.full_name) return passedRepo;
  const stateRepo = window.RR_STATE?.episode?.repo;
  if (stateRepo?.full_name) return stateRepo;
  const id = currentEpisodeIdFromDom();
  if (!id) return null;
  try {
    const r = await fetch(staticUrl(`/episodes/${id}.json`), { cache: "no-store" });
    if (r.ok) {
      const ep = await r.json();
      if (ep?.repo?.full_name) return ep.repo;
    }
  } catch {}
  return null;
}

export function createSync({ segments, transcriptEl, codeFileEl, codeLinesEl, codeBodyEl, onSeek, repo }) {
  let repoInfo = repo?.full_name ? repo : null;
  resolveRepoInfo(repo).then((r) => {
    if (r) { repoInfo = r; applyLinks(); }
  });

  transcriptEl.innerHTML = "";
  const rows = new Map(); // seg.i → row element
  segments.forEach((s) => {
    const row = segRow(s, "seg");
    row.addEventListener("click", () => onSeek?.(s.start + 0.01));
    transcriptEl.appendChild(row);
    rows.set(s.i, row);
  });

  // Manual scroll suppresses auto-scroll briefly.
  let manualUntil = 0;
  const noteManual = () => { manualUntil = Date.now() + SCROLL_SUPPRESS_MS; };
  transcriptEl.addEventListener("wheel", noteManual, { passive: true });
  transcriptEl.addEventListener("touchmove", noteManual, { passive: true });

  // ── Code card: filename tab + cited block are GitHub deep links ──
  // https://github.com/<full_name>/blob/<branch>/<file>#L<start>-L<end>
  let shownKey = null; // "file:start-end" of what's currently displayed
  let currentCitation = null;

  // Filename tab: keep it a plain element (owned by index.html/app.js), just add a
  // trailing ↗ affordance + pointer cursor + click-to-open, without altering its id.
  const fileArrow = document.createElement("span");
  fileArrow.textContent = " ↗";
  fileArrow.style.opacity = "0.7";
  fileArrow.style.marginLeft = "2px";
  codeFileEl.appendChild(fileArrow);
  codeFileEl.style.cursor = "pointer";
  codeFileEl.title = "Open on GitHub";
  codeFileEl.addEventListener("click", () => openCitation());

  codeBodyEl.style.cursor = "pointer";
  codeBodyEl.title = "Open on GitHub";
  codeBodyEl.addEventListener("mouseenter", () => {
    codeBodyEl.style.boxShadow = "inset 0 0 0 1px var(--amber)";
  });
  codeBodyEl.addEventListener("mouseleave", () => {
    codeBodyEl.style.boxShadow = "";
  });
  codeBodyEl.addEventListener("click", (e) => {
    // Don't hijack text selection drags.
    if (window.getSelection?.().toString()) return;
    openCitation();
  });

  function openCitation() {
    const url = citationUrl(repoInfo, currentCitation);
    if (url) window.open(url, "_blank", "noopener");
  }

  function applyLinks() {
    // Re-apply once repoInfo resolves (it may arrive after the first citation render).
    const url = citationUrl(repoInfo, currentCitation);
    const has = !!url;
    codeFileEl.style.cursor = has ? "pointer" : "default";
    codeBodyEl.style.cursor = has ? "pointer" : "default";
    fileArrow.style.display = has ? "" : "none";
  }

  function showCitation(c) {
    if (!c) return; // keep previous code card on citation-less segments
    const key = `${c.file}:${c.start_line}-${c.end_line}`;
    currentCitation = c;
    if (key !== shownKey) {
      shownKey = key;
      codeFileEl.textContent = c.file; // clears fileArrow too — re-append it
      codeFileEl.appendChild(fileArrow);
      codeLinesEl.textContent = `L${c.start_line}–${c.end_line}`;
      codeBodyEl.innerHTML = c.code_html;
      const cited = codeBodyEl.querySelector(".line.cited");
      if (cited) {
        // Center the first cited line inside the code panel only (no page scroll).
        codeBodyEl.scrollTop = cited.offsetTop - codeBodyEl.clientHeight / 2 + cited.offsetHeight / 2;
      }
    }
    applyLinks();
  }

  // ── Row activation, shared by main + qa lanes ──
  function activate(segs, rowMap, t, prev) {
    const seg = findActive(segs, t);
    const cur = seg ? rowMap.get(seg.i) : null;
    if (cur !== prev.row) {
      prev.row?.classList.remove("active");
      cur?.classList.add("active");
      prev.row = cur;
      if (cur && Date.now() >= manualUntil) {
        cur.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }
    if (seg) showCitation(seg.citation);
  }

  const mainState = { row: null };

  return {
    update(t) {
      activate(segments, rows, t, mainState);
    },

    appendQa(qa, opts) {
      const divider = document.createElement("div");
      divider.className = "seg qa";
      divider.style.cursor = "default";
      divider.innerHTML = `<span class="font-mono2 text-[11px]" style="color: var(--teal)">☎ "${qa.question}"</span>`;
      transcriptEl.appendChild(divider);

      const qaRows = new Map();
      qa.segments.forEach((s) => {
        const row = segRow(s, "seg qa");
        if (opts?.onPlay) row.addEventListener("click", () => opts.onPlay());
        else row.style.cursor = "default";
        transcriptEl.appendChild(row);
        qaRows.set(s.i, row);
      });
      divider.scrollIntoView({ block: "nearest", behavior: "smooth" });

      const qaState = { row: null };
      return {
        update(t) {
          activate(qa.segments, qaRows, t, qaState);
        },
        deactivate() {
          qaState.row = null;
          qaRows.forEach((r) => r.classList.remove("active"));
        },
      };
    },
  };
}
