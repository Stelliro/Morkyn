/*
 * The native title bar, dressed in the theme. Only does anything inside
 * Mørkyn's own window (morkyn_app.py exposes window.pywebview.api); in a
 * browser it is inert. Loaded by index.html and popout.html.
 *
 * Caption = the void (--bg), title text = the thread (--thread), and the
 * window border is a dim thread line. Re-sent whenever data-theme changes,
 * so the frame follows the theme picker (and pop-outs follow the game).
 */
(function () {
  "use strict";

  var isPopout = /\/popout(\.html)?$/.test(location.pathname);
  var frameId = isPopout ? (new URLSearchParams(location.search).get("tab") || "player").toLowerCase() : "main";
  var lastSent = "";

  function hex(r, g, b) {
    return "#" + [r, g, b].map(function (n) {
      var v = Math.max(0, Math.min(255, Math.round(Number(n) || 0)));
      return (v < 16 ? "0" : "") + v.toString(16);
    }).join("");
  }

  // Resolve a CSS colour expression (tokens, color-mix) to #rrggbb via a probe.
  function resolve(expr) {
    var probe = document.createElement("span");
    probe.style.display = "none";
    probe.style.color = expr;
    document.documentElement.appendChild(probe);
    var value = getComputedStyle(probe).color || "";
    probe.remove();
    var m = value.match(/rgba?\(([^)]+)\)/);
    if (m) {
      var p = m[1].split(/[\s,/]+/).filter(Boolean);
      return hex(p[0], p[1], p[2]);
    }
    m = value.match(/color\(srgb\s+([^)]+)\)/);
    if (m) {
      var q = m[1].split(/[\s/]+/).filter(Boolean);
      return hex(q[0] * 255, q[1] * 255, q[2] * 255);
    }
    return "";
  }

  function sync() {
    var api = window.pywebview && window.pywebview.api;
    if (!api || typeof api.set_frame_colors !== "function") return;
    var colors = {
      caption: resolve("var(--bg)"),
      text: resolve("var(--thread)"),
      border: resolve("color-mix(in srgb, var(--thread) 34%, var(--bg))"),
    };
    if (!colors.caption || !colors.text) return;
    var key = JSON.stringify(colors);
    if (key === lastSent) return;
    lastSent = key;
    var sent = api.set_frame_colors(frameId, colors);
    if (sent && typeof sent.catch === "function") sent.catch(function () { lastSent = ""; });
  }

  new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("pywebviewready", sync);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sync);
  else sync();
})();
