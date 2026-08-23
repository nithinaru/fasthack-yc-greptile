// Repo Radio frontend config.
// Lane D writes API_BASE via a SYNC: commit when App Runner is live.
// USE_MOCKS=true keeps the whole page functional with zero backend.
window.RR_CONFIG = {
  USE_MOCKS: true,
  API_BASE: "",            // e.g. "https://xxxx.us-west-2.awsapprunner.com"
  MEMORY_URL_LIVE: "/memory.json",
  MEMORY_URL_MOCK: "mock/memory.json",
  EPISODE_PROBE_MAX: 25,   // discover episodes by probing /episodes/ep-000..NNN.json
  DEFAULT_USER: "demo@reporadio.fm",
};
