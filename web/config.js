// Repo Radio frontend config.
// API_BASE / STATIC_BASE default to "" (relative paths) so the same page works
// locally (python3 -m http.server from web/) and served from Modal /serve.
// All API calls go `${API_BASE}/api/...`; all static asset fetches go
// `${STATIC_BASE}/episodes/...`, `${STATIC_BASE}/audio/...`, `${STATIC_BASE}/memory.json`.
window.RR_CONFIG = {
  USE_MOCKS: false,
  API_BASE: "",             // e.g. "https://xxxx.modal.run" if API is split from static
  STATIC_BASE: "",          // e.g. "https://xxxx.modal.run" for the Modal /serve static root
  EPISODE_PROBE_MAX: 25,    // discover episodes by probing /episodes/ep-000..NNN.json
  DEFAULT_USER: "demo@reporadio.fm",
};
