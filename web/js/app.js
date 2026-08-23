// Repo Radio — app orchestration. Loads episode data, wires player/sync/wallet.
// Data contract: contracts/episode.schema.json (frozen). No build step, ES modules.
import { createPlayer } from "./player.js";
import { createSync } from "./sync.js";
import { initWallet } from "./wallet.js";

const CFG = window.RR_CONFIG;
const $ = (id) => document.getElementById(id);

const state = {
  episodes: [],       // [{id, title, verdict, repo, _url}]
  episode: null,      // full episode JSON currently loaded
  player: null,
  sync: null,
  qaAudio: null,      // native Audio element for Q&A answer playback
};

// ── Episode discovery: probe /episodes/ep-000.json upward (no index contract) ──
async function discoverEpisodes() {
  const found = [];
  for (let n = 0; n < CFG.EPISODE_PROBE_MAX; n++) {
    const id = `ep-${String(n).padStart(3, "0")}`;
    try {
      const r = await fetch(`episodes/${id}.json`, { cache: "no-store" });
      if (!r.ok) { if (found.length) break; else continue; }
      found.push(await r.json());
    } catch { if (found.length) break; }
  }
  return found;
}

function fmtTime(t) {
  t = Math.max(0, Math.floor(t));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

// ── Hero ──
function renderHero(ep) {
  const repo = ep.repo || {};
  const rn = $("repo-name");
  rn.textContent = repo.full_name || "—";
  rn.href = repo.url || "#";
  $("repo-meta").textContent =
    `${repo.language || ""} · ★ ${Number(repo.stars_at_airtime || 0).toLocaleString()} · +${repo.velocity_per_hr || 0}/hr`;
  $("ep-title").textContent = ep.title;
  const badge = $("verdict-badge");
  badge.textContent = ep.verdict;
  badge.className = `badge badge-${ep.verdict} mt-3 shrink-0`;
  $("ep-date").textContent = `${ep.id.toUpperCase()} · ${ep.date}`;
  document.title = `${ep.title} — Repo Radio 102.3 FM`;
}

// ── Episode list (sidebar) ──
function renderEpisodeList() {
  const el = $("episode-list");
  el.innerHTML = "";
  [...state.episodes].reverse().forEach((ep) => {
    const active = state.episode && ep.id === state.episode.id;
    const row = document.createElement("button");
    row.className =
      "w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-white/[.02] transition-colors" +
      (active ? " bg-white/[.03]" : "");
    row.style.borderTop = "1px solid var(--border)";
    row.innerHTML = `
      <span class="font-mono2 text-[11px]" style="color: var(--amber-dim)">${ep.id.replace("ep-", "EP ")}</span>
      <span class="flex-1 min-w-0">
        <span class="block text-[13px] truncate" style="color: var(--text)">${ep.repo?.full_name || ""}</span>
        <span class="block font-mono2 text-[10px] truncate" style="color: var(--text-2)">${ep.title}</span>
      </span>
      <span class="w-2 h-2 rounded-full vdot-${ep.verdict} shrink-0" title="${ep.verdict}"></span>
      ${active ? '<span class="eq paused" id="eq-now"><span></span><span></span><span></span><span></span><span></span></span>' : ""}`;
    row.addEventListener("click", () => { if (!active) loadEpisode(ep.id); });
    el.appendChild(row);
  });
}

// ── Host's Memory panel (memory.json shape is uncontracted — render defensively) ──
async function renderMemory() {
  const url = CFG.USE_MOCKS ? CFG.MEMORY_URL_MOCK : CFG.MEMORY_URL_LIVE;
  let data = null;
  try { const r = await fetch(url, { cache: "no-store" }); if (r.ok) data = await r.json(); } catch {}
  const panel = $("memory-panel");
  const entries = Array.isArray(data) ? data : (data && (data.entries || data.observations)) || [];
  if (!entries.length) {
    panel.innerHTML = `<div class="font-mono2 text-[11px]" style="color: var(--text-2)">// no memories yet — the host is young</div>`;
    return;
  }
  panel.innerHTML = entries.map((e) => `
    <div class="border-l-2 pl-3" style="border-color: var(--amber-dim)">
      <div class="flex items-center gap-2">
        <span class="font-mono2 text-[10px]" style="color: var(--amber)">${e.episode_id || e.episode || ""}</span>
        <span class="font-mono2 text-[11px]" style="color: var(--text)">${e.repo || ""}</span>
        ${e.verdict ? `<span class="w-1.5 h-1.5 rounded-full vdot-${e.verdict}"></span>` : ""}
        <span class="flex-1"></span>
        <span class="font-mono2 text-[9px]" style="color: var(--text-2)">${(e.ts || e.date || "").slice(0, 10)}</span>
      </div>
      <ul class="mt-1 space-y-0.5">
        ${(e.facts || e.notes || (e.note ? [e.note] : [])).map((f) => `<li class="text-[12px] leading-snug" style="color: var(--text-2)">· ${f}</li>`).join("")}
      </ul>
    </div>`).join("");
}

function wireMemoryToggle() {
  $("memory-toggle").addEventListener("click", () => {
    const p = $("memory-panel");
    const open = p.classList.toggle("hidden");
    $("memory-caret").style.transform = open ? "" : "rotate(90deg)";
  });
}

// ── Play state ↔ chrome (lamp, glow, eq, button icon) ──
function setPlayingUI(playing) {
  $("onair").classList.toggle("live", playing);
  document.body.classList.toggle("playing", playing);
  $("icon-play").classList.toggle("hidden", playing);
  $("icon-pause").classList.toggle("hidden", !playing);
  const eq = $("eq-now");
  if (eq) eq.classList.toggle("paused", !playing);
}

// ── Q&A playback: answer plays "on air" with its own audio + same sync logic ──
function playQaSegment(qa) {
  if (!qa) return;
  state.player?.pause();
  if (state.qaAudio) { state.qaAudio.pause(); state.qaAudio = null; }
  const handle = state.sync.appendQa(qa);
  const audio = new Audio(qa.audio_url);
  state.qaAudio = audio;
  // Answer segments may sit mid-file (mock replays a stretch of the episode):
  // start at the first segment and stop just past the last.
  const t0 = qa.segments[0]?.start ?? 0;
  const tEnd = (qa.segments[qa.segments.length - 1]?.end ?? Infinity) + 0.35;
  audio.addEventListener("loadedmetadata", () => { if (t0 > 0.1) audio.currentTime = t0; });
  audio.addEventListener("timeupdate", () => {
    handle.update(audio.currentTime);
    if (audio.currentTime >= tEnd) { audio.pause(); handle.deactivate(); }
  });
  audio.addEventListener("play", () => setPlayingUI(true));
  audio.addEventListener("pause", () => setPlayingUI(false));
  audio.addEventListener("ended", () => { setPlayingUI(false); handle.deactivate(); });
  audio.play().catch(() => {});
}

// ── Episode load / boot ──
async function loadEpisode(id) {
  const ep = state.episodes.find((e) => e.id === id) || state.episodes[state.episodes.length - 1];
  if (!ep) return;
  state.episode = ep;
  if (state.qaAudio) { state.qaAudio.pause(); state.qaAudio = null; }
  renderHero(ep);
  renderEpisodeList();

  // sync (owns transcript + code card)
  state.sync = createSync({
    segments: ep.segments,
    transcriptEl: $("transcript"),
    codeFileEl: $("code-file"),
    codeLinesEl: $("code-lines"),
    codeBodyEl: $("code-body"),
    onSeek: (t) => state.player?.seek(t),
  });
  (ep.qa_segments || []).forEach((qa) => state.sync.appendQa(qa, { onPlay: () => playQaSegment(qa) }));

  // player
  if (state.player) state.player.destroy?.();
  $("waveform").innerHTML = "";
  state.player = await createPlayer({
    container: $("waveform"),
    audioUrl: ep.audio.url.startsWith("/") ? ep.audio.url.slice(1) : ep.audio.url,
    peaks: ep.audio.peaks,
    duration: ep.audio.duration_s,
    onTime: (t) => { $("time-cur").textContent = fmtTime(t); state.sync.update(t); },
    onPlayState: (playing) => { if (playing && state.qaAudio) { state.qaAudio.pause(); } setPlayingUI(playing); },
    onReady: (dur) => { $("time-dur").textContent = fmtTime(dur || ep.audio.duration_s); },
  });
  $("time-dur").textContent = fmtTime(ep.audio.duration_s);
}

async function boot() {
  wireMemoryToggle();
  $("play-btn").addEventListener("click", () => state.player?.toggle());
  state.episodes = await discoverEpisodes();
  if (!state.episodes.length) {
    $("ep-title").textContent = "Dead air… no episodes found.";
    return;
  }
  const want = new URLSearchParams(location.search).get("ep");
  await loadEpisode(want || state.episodes[state.episodes.length - 1].id);
  renderMemory();
  initWallet({
    config: CFG,
    els: {
      chip: $("wallet-chip"), credits: $("wallet-credits"),
      askForm: $("ask-form"), askInput: $("ask-input"), askBtn: $("ask-btn"),
      askStatus: $("ask-status"), tiers: $("topup-tiers"), topupStatus: $("topup-status"),
    },
    getEpisode: () => state.episode,
    onQaSegment: (qa) => playQaSegment(qa),
  });
}

boot();
