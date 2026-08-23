// C4 — wallet, top-up tiers, and the ask-the-host call-in flow.
// Contract: contracts/wallet_api.md (frozen). Mock mode works with zero backend.

// PRICING FROZEN (PRD §3.4 / v2 notes): $1→10, $5→55, $10→120. Tier values sent
// to POST /api/topup are 1|5|10 (dollars).
const TIER_CREDITS = { 1: 10, 5: 55, 10: 120 };
const MOCK_KEY = "rr_mock_credits";
const USER_KEY = "rr_user";

const STATUS_LINES = [
  "☎ patching you through…",
  "the host is reading the code…",
  "recording the answer…",
];

export function initWallet({ config, els, getEpisode, onQaSegment }) {
  let userId = (localStorage.getItem(USER_KEY) || "").toLowerCase();
  if (!userId) {
    userId = config.DEFAULT_USER.toLowerCase();
    localStorage.setItem(USER_KEY, userId);
  }

  let credits = null; // null until first known balance
  let animRaf = 0;
  let animDone = 0;

  // ── Balance display: animated count between values ──
  function setCredits(next, { animate = true } = {}) {
    const prev = credits;
    credits = next;
    updateStrip();
    if (!animate || prev === null || prev === next) {
      els.credits.textContent = String(next);
      return;
    }
    cancelAnimationFrame(animRaf);
    clearTimeout(animDone);
    els.credits.classList.add("credit-pop");
    const t0 = performance.now(), dur = 800;
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      els.credits.textContent = String(Math.round(prev + (next - prev) * eased));
      if (p < 1) animRaf = requestAnimationFrame(tick);
    };
    animRaf = requestAnimationFrame(tick);
    // rAF can throttle to a halt in background/occluded tabs — force completion.
    animDone = setTimeout(() => {
      cancelAnimationFrame(animRaf);
      els.credits.textContent = String(next);
      els.credits.classList.remove("credit-pop");
    }, dur + 100);
  }

  // ── Zero balance → show tiers; positive → show ask form ──
  function updateStrip() {
    const broke = (credits ?? 0) < 1;
    els.askForm.style.display = broke ? "none" : "";
    els.tiers.classList.toggle("hidden", !broke);
    els.tiers.style.display = broke ? "flex" : "";
  }

  // ── Ask-status rotation ──
  let statusTimer = 0;
  function startAskStatus() {
    els.askInput.disabled = true;
    els.askBtn.disabled = true;
    els.askStatus.classList.remove("hidden");
    let i = 0;
    els.askStatus.textContent = STATUS_LINES[0];
    statusTimer = setInterval(() => {
      i = (i + 1) % STATUS_LINES.length;
      els.askStatus.textContent = STATUS_LINES[i];
    }, 1500);
  }
  function stopAskStatus() {
    clearInterval(statusTimer);
    els.askInput.disabled = false;
    els.askBtn.disabled = false;
    els.askStatus.classList.add("hidden");
  }
  function askError(msg) {
    clearInterval(statusTimer);
    els.askInput.disabled = false;
    els.askBtn.disabled = false;
    els.askStatus.classList.remove("hidden");
    els.askStatus.textContent = msg;
    setTimeout(() => els.askStatus.classList.add("hidden"), 4000);
  }

  function deliver(qa) {
    stopAskStatus();
    els.askInput.value = "";
    onQaSegment(qa);
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ══ MOCK mode ══
  function mockBalance() {
    let v = localStorage.getItem(MOCK_KEY);
    if (v === null) { v = "100"; localStorage.setItem(MOCK_KEY, v); }
    return parseInt(v, 10) || 0;
  }
  function mockSetBalance(v) {
    localStorage.setItem(MOCK_KEY, String(v));
    setCredits(v);
  }

  function mockQaSegment(question) {
    const ep = getEpisode();
    // Replay the last cited stretch of the episode so highlighting works offline.
    const cited = [...ep.segments].reverse().find((s) => s.citation);
    return {
      question,
      audio_url: ep.audio.url,
      segments: [{
        i: 0,
        start: cited.start,
        end: cited.end,
        text: "(mock answer) Good question — the honest answer lives in the scheduler: decaying priorities mean stale tasks fall out of line, and that's the one pattern here worth stealing.",
        citation: cited.citation,
      }],
    };
  }

  async function mockAsk(question) {
    if (mockBalance() < 1) { updateStrip(); return; }
    startAskStatus();
    mockSetBalance(mockBalance() - 1);
    await sleep(2800);
    deliver(mockQaSegment(question));
  }

  async function mockTopup(tier) {
    els.topupStatus.textContent = "redirecting to Stripe checkout…";
    await sleep(1400);
    els.topupStatus.textContent = "payment confirmed ✓";
    mockSetBalance(mockBalance() + TIER_CREDITS[tier]);
    setTimeout(() => { els.topupStatus.textContent = ""; }, 3000);
  }

  // ══ LIVE mode ══
  const base = config.API_BASE;

  async function fetchWallet() {
    try {
      const r = await fetch(`${base}/api/wallet/${encodeURIComponent(userId)}`);
      if (!r.ok) return null;
      return (await r.json()).credits;
    } catch { return null; }
  }

  async function refreshWallet() {
    const c = await fetchWallet();
    if (c !== null && c !== credits) setCredits(c);
  }

  async function liveTopup(tier) {
    els.topupStatus.textContent = "redirecting to Stripe checkout…";
    try {
      const r = await fetch(`${base}/api/topup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, tier: Number(tier) }),
      });
      if (!r.ok) throw new Error();
      const { checkout_url } = await r.json();
      window.location = checkout_url;
    } catch {
      els.topupStatus.textContent = "top-up failed — try again";
      setTimeout(() => { els.topupStatus.textContent = ""; }, 4000);
    }
  }

  // Back from Stripe: poll until the webhook lands the credits.
  async function pollAfterTopup() {
    const before = credits ?? 0;
    for (let i = 0; i < 15; i++) {
      await sleep(1000);
      const c = await fetchWallet();
      if (c !== null && c > before) { setCredits(c); return; }
    }
  }

  async function liveAsk(question) {
    startAskStatus();
    let jobId;
    try {
      const r = await fetch(`${base}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, episode_id: getEpisode().id, question }),
      });
      if (r.status === 402) {
        stopAskStatus();
        setCredits(0);
        els.topupStatus.textContent = "no credits";
        return;
      }
      if (!r.ok) throw new Error();
      jobId = (await r.json()).job_id;
    } catch {
      askError("call dropped — the line is busy, try again");
      return;
    }
    for (let waited = 0; waited < 120000; waited += 2000) {
      await sleep(2000);
      try {
        const r = await fetch(`${base}/api/ask/${encodeURIComponent(jobId)}`);
        if (!r.ok) throw new Error();
        const j = await r.json();
        if (j.status === "done") {
          setCredits(Math.max(0, (credits ?? 1) - 1));
          deliver(j.qa_segment);
          refreshWallet();
          return;
        }
      } catch {
        askError("call dropped — the line is busy, try again");
        return;
      }
    }
    askError("the host never picked up — credit may still be spent");
  }

  // ── Wiring ──
  els.askForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = els.askInput.value.trim();
    if (!q || els.askBtn.disabled) return;
    if (config.USE_MOCKS) mockAsk(q); else liveAsk(q);
  });

  els.tiers.querySelectorAll(".tier-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tier = Number(btn.dataset.tier);
      if (config.USE_MOCKS) mockTopup(tier); else liveTopup(tier);
    });
  });

  // ── Boot ──
  if (config.USE_MOCKS) {
    setCredits(mockBalance(), { animate: false });
  } else {
    refreshWallet().then(() => {
      if (location.search.includes("topup")) pollAfterTopup();
    });
    setInterval(refreshWallet, 10000);
  }
}
