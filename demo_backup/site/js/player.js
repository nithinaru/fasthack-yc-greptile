// Repo Radio — audio player. Primary: wavesurfer v7 (CDN, pre-computed peaks).
// Fallback: native <audio> + CSS progress track with the same returned API.
// createPlayer never throws — it always resolves to a working player object.

// Vendored copy first (zero-network demo path), CDN as backup.
const WAVESURFER_LOCAL = new URL("../vendor/wavesurfer.esm.js", import.meta.url).href;
const WAVESURFER_CDN = "https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js";
const WS_ERROR_TIMEOUT_MS = 6000;

export async function createPlayer({ container, audioUrl, peaks, duration, onTime, onPlayState, onReady }) {
  try {
    return await createWavesurferPlayer({ container, audioUrl, peaks, duration, onTime, onPlayState, onReady });
  } catch {
    return createFallbackPlayer({ container, audioUrl, duration, onTime, onPlayState, onReady });
  }
}

// ── Primary path: wavesurfer v7 bar waveform ──
async function createWavesurferPlayer({ container, audioUrl, peaks, duration, onTime, onPlayState, onReady }) {
  const { default: WaveSurfer } = await import(WAVESURFER_LOCAL).catch(() => import(WAVESURFER_CDN));

  const ws = WaveSurfer.create({
    container,
    url: audioUrl,
    peaks: [peaks], // pre-computed — renders instantly, no audio fetch/decode
    duration,
    barWidth: 3,
    barGap: 2,
    barRadius: 3,
    height: 72,
    waveColor: "#7A5A1E",
    progressColor: "#FFB020",
    cursorColor: "#FFB020",
    cursorWidth: 1,
    normalize: true,
  });

  ws.on("timeupdate", (t) => onTime?.(t));
  ws.on("play", () => onPlayState?.(true));
  ws.on("pause", () => onPlayState?.(false));

  // Degrade to fallback if wavesurfer errors before it's ready (~6s window).
  await new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, WS_ERROR_TIMEOUT_MS); // no error by then → assume fine
    ws.once("ready", () => { clearTimeout(timer); resolve(); });
    ws.once("error", (e) => { clearTimeout(timer); try { ws.destroy(); } catch {} reject(e); });
  });
  onReady?.(ws.getDuration() || duration);

  return {
    play: () => ws.play(),
    pause: () => ws.pause(),
    toggle: () => ws.playPause(),
    seek: (t) => ws.setTime(t),
    isPlaying: () => ws.isPlaying(),
    getCurrentTime: () => ws.getCurrentTime(),
    destroy: () => { try { ws.destroy(); } catch {} },
  };
}

// ── Fallback path: native Audio + slim amber progress track ──
function createFallbackPlayer({ container, audioUrl, duration, onTime, onPlayState, onReady }) {
  const audio = new Audio(audioUrl);
  audio.preload = "metadata";

  container.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.style.cssText = "height:72px;display:flex;align-items:center;cursor:pointer";
  const track = document.createElement("div");
  track.style.cssText = "position:relative;width:100%;height:4px;border-radius:2px;background:#26263A;overflow:hidden";
  const fill = document.createElement("div");
  fill.style.cssText = "position:absolute;inset:0 auto 0 0;width:0%;border-radius:2px;background:#FFB020";
  track.appendChild(fill);
  wrap.appendChild(track);
  container.appendChild(wrap);

  const dur = () => audio.duration || duration || 1;

  audio.addEventListener("timeupdate", () => {
    fill.style.width = `${(audio.currentTime / dur()) * 100}%`;
    onTime?.(audio.currentTime);
  });
  audio.addEventListener("play", () => onPlayState?.(true));
  audio.addEventListener("pause", () => onPlayState?.(false));
  audio.addEventListener("loadedmetadata", () => onReady?.(audio.duration));

  wrap.addEventListener("click", (e) => {
    const r = wrap.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * dur();
  });

  return {
    play: () => audio.play().catch(() => {}),
    pause: () => audio.pause(),
    toggle: () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()),
    seek: (t) => { audio.currentTime = t; },
    isPlaying: () => !audio.paused,
    getCurrentTime: () => audio.currentTime,
    destroy: () => { audio.pause(); audio.src = ""; },
  };
}
