// Repo Radio — episode cover art hookup (M4). Self-contained, defensive:
// no imports from app.js, no assumptions beyond stable DOM ids. Covers live
// at /covers/ep-NNN.svg; a 404 means we silently leave the UI untouched.
(function () {
  "use strict";

  var checked = {}; // epid -> true (exists) | false (404) | "pending"

  function coverUrl(epid) {
    return "/covers/" + epid + ".svg";
  }

  // Probe once per episode id; cb(true|false) possibly async.
  function probe(epid, cb) {
    if (typeof checked[epid] === "boolean") return cb(checked[epid]);
    if (checked[epid] === "pending") return; // another probe in flight; refresh loop will retry
    checked[epid] = "pending";
    var img = new Image();
    img.onload = function () { checked[epid] = true; cb(true); };
    img.onerror = function () { checked[epid] = false; cb(false); };
    img.src = coverUrl(epid);
  }

  function epIdFrom(text) {
    var m = /EP[\s-]?(\d{3})/i.exec(text || "");
    return m ? "ep-" + m[1] : null;
  }

  // (a) thumbnails in the sidebar episode list rows.
  function decorateList() {
    var list = document.getElementById("episode-list");
    if (!list) return;
    Array.prototype.forEach.call(list.children, function (row) {
      if (row.querySelector("img.cover-thumb")) return;
      var epid = epIdFrom(row.textContent);
      if (!epid) return;
      probe(epid, function (ok) {
        if (!ok || row.querySelector("img.cover-thumb")) return;
        var img = document.createElement("img");
        img.className = "cover-thumb";
        img.src = coverUrl(epid);
        img.alt = "";
        img.style.cssText =
          "width:40px;height:40px;border-radius:6px;flex-shrink:0;" +
          "object-fit:cover;border:1px solid rgba(255,176,32,.18)";
        row.insertBefore(img, row.firstChild);
      });
    });
  }

  // (b) hero art for the currently playing episode. Current ep id is read
  // from #ep-date ("EP-001 · 2026-08-23"), which app.js keeps in sync.
  function decorateHero() {
    var dateEl = document.getElementById("ep-date");
    var epid = epIdFrom(dateEl && dateEl.textContent);
    if (!epid) return;
    var existing = document.getElementById("cover-hero");
    if (existing && existing.dataset.ep === epid) return;
    probe(epid, function (ok) {
      if (!ok) { if (existing) existing.remove(); return; }
      var title = document.getElementById("ep-title");
      if (!title || !title.parentElement) return;
      var img = existing || document.createElement("img");
      img.id = "cover-hero";
      img.dataset.ep = epid;
      img.src = coverUrl(epid);
      img.alt = "Episode cover";
      img.style.cssText =
        "width:96px;height:96px;border-radius:10px;object-fit:cover;" +
        "flex-shrink:0;margin-left:12px;border:1px solid rgba(255,176,32,.22);" +
        "box-shadow:0 4px 24px rgba(0,0,0,.5)";
      if (!existing) {
        // Title sits in a flex row with the verdict badge — append alongside.
        title.parentElement.appendChild(img);
      }
    });
  }

  function refresh() { decorateList(); decorateHero(); }

  function start() {
    refresh();
    // MutationObserver catches list re-renders and hero updates from app.js;
    // slow interval is a belt-and-braces fallback.
    try {
      new MutationObserver(refresh).observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    } catch (e) { /* fall through to interval */ }
    setInterval(refresh, 3000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
