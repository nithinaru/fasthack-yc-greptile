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

export function createSync({ segments, transcriptEl, codeFileEl, codeLinesEl, codeBodyEl, onSeek }) {
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

  // ── Code card ──
  let shownKey = null; // "file:start-end" of what's currently displayed
  function showCitation(c) {
    if (!c) return; // keep previous code card on citation-less segments
    const key = `${c.file}:${c.start_line}-${c.end_line}`;
    if (key === shownKey) return;
    shownKey = key;
    codeFileEl.textContent = c.file;
    codeLinesEl.textContent = `L${c.start_line}–${c.end_line}`;
    codeBodyEl.innerHTML = c.code_html;
    const cited = codeBodyEl.querySelector(".line.cited");
    if (cited) {
      // Center the first cited line inside the code panel only (no page scroll).
      codeBodyEl.scrollTop = cited.offsetTop - codeBodyEl.clientHeight / 2 + cited.offsetHeight / 2;
    }
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
