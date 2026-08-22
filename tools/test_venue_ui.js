/**
 * Regression: the venue subsystem must be visible in the browser UI.
 *
 * Venues shipped server-side with no UI at all — `static/app.js` did not
 * contain the word "venue". Entering a shop only changed the location name, so
 * a player could not see that a smithy was on this square, could not tell it
 * was shut, and had no indication that stepping outside was a move. Everything
 * needed already rode in `state.current_location`; the UI simply threw it away.
 *
 * Exit 0 = venues render, closed state shows, exit is offered
 * Exit 1 = a case regressed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

function extractFunction(source, name) {
  const start = source.indexOf(`\nfunction ${name}(`);
  if (start < 0) throw new Error(`function ${name} not found in app.js`);
  let i = source.indexOf("{", start);
  let depth = 0;
  let inString = null;
  let inLine = false;
  let inBlock = false;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    const next = source[i + 1];
    if (inLine) { if (ch === "\n") inLine = false; continue; }
    if (inBlock) { if (ch === "*" && next === "/") { inBlock = false; i += 1; } continue; }
    if (inString) {
      if (ch === "\\") { i += 1; continue; }
      if (ch === inString) inString = null;
      continue;
    }
    if (ch === "/" && next === "/") { inLine = true; i += 1; continue; }
    if (ch === "/" && next === "*") { inBlock = true; i += 1; continue; }
    if (ch === '"' || ch === "'" || ch === "`") { inString = ch; continue; }
    if (ch === "{") depth += 1;
    else if (ch === "}") { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

/** Minimal stand-in for the one element the renderer writes to. */
function makeEl() {
  return {
    innerHTML: "",
    hidden: false,
    _classes: new Set(),
    classList: {
      add(c) { this._owner._classes.add(c); },
      remove(c) { this._owner._classes.delete(c); },
      contains(c) { return this._owner._classes.has(c); },
    },
    setAttribute() {},
    get isHidden() { return this.hidden === true; },
  };
}

function buildSandbox() {
  const source = fs.readFileSync(APP_JS, "utf8");
  const code = [
    extractFunction(source, "escapeHtml"),
    extractFunction(source, "updateVenueLine"),
  ].join("\n\n");
  const el = makeEl();
  el.classList._owner = el;
  const sandbox = { venueLine: el, state: null, console };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return { sandbox, el };
}

const OUTSIDE = {
  current_location: {
    name: "Brimmer Square",
    inside_venue: false,
    venues_here: [
      { code: "L2", name: "Brimmer Apothecary", kind: "apothecary", open: true, hours: "08:00-18:00" },
      { code: "L3", name: "Gedra Forge", kind: "smithy", open: false, hours: "06:00-16:00" },
    ],
  },
};

const INSIDE = {
  current_location: {
    name: "Brimmer Apothecary",
    inside_venue: true,
    exit_to: "Brimmer Square",
    keeper: { code: "A", name: "Jethook", role: "apothecary" },
    venues_here: [
      { code: "L3", name: "Gedra Forge", kind: "smithy", open: true, hours: "06:00-16:00" },
    ],
  },
};

const BARE = { current_location: { name: "Mosswake Road", inside_venue: false, venues_here: [] } };

function main() {
  let ctx;
  try {
    ctx = buildSandbox();
  } catch (err) {
    console.error("harness error:", err.message);
    return 2;
  }
  const { sandbox, el } = ctx;
  const failures = [];

  // 1. Venues on the square are listed and clickable.
  sandbox.updateVenueLine(OUTSIDE);
  if (el.hidden) failures.push("venue line hidden while venues are present");
  if (!el.innerHTML.includes("Brimmer Apothecary")) failures.push("open venue not listed");
  if (!el.innerHTML.includes("Gedra Forge")) failures.push("closed venue not listed");
  if (!el.innerHTML.includes('data-venue-enter="Brimmer Apothecary"')) {
    failures.push("open venue is not clickable");
  }

  // 2. Closed is stated, not merely implied.
  if (!/venueClosed/.test(el.innerHTML)) failures.push("closed venue not marked closed");
  if (!el.innerHTML.includes("(closed)")) failures.push("closed venue has no visible label");
  // Inspect each button on its own. Splitting the whole string on a venue name
  // catches that venue's *own* class attribute and reports a false failure.
  const buttons = el.innerHTML.match(/<button[^>]*data-venue-enter="[^"]*"[^>]*>.*?<\/button>/g) || [];
  const buttonFor = (name) => buttons.find((b) => b.includes(`data-venue-enter="${name}"`)) || "";
  if (/venueClosed/.test(buttonFor("Brimmer Apothecary"))) {
    failures.push("open venue wrongly marked closed");
  }
  if (!/venueClosed/.test(buttonFor("Gedra Forge"))) {
    failures.push("closed venue not marked closed on its own chip");
  }

  // 3. Inside a venue: keeper named, way out offered.
  sandbox.updateVenueLine(INSIDE);
  if (!el.innerHTML.includes("Jethook")) failures.push("bound keeper not shown inside a venue");
  if (!el.innerHTML.includes('data-venue-exit="Brimmer Square"')) failures.push("no way out offered");
  if (!el.innerHTML.includes("Inside:")) failures.push("inside state not labelled");

  // 4. Nothing here means nothing shown — no empty strip.
  sandbox.updateVenueLine(BARE);
  if (!el.hidden) failures.push("venue line left visible with no venues");
  if (el.innerHTML !== "") failures.push("venue line kept stale content");

  // 5. A venue with no hours must not be called closed by accident.
  sandbox.updateVenueLine({
    current_location: {
      name: "Waystone", inside_venue: false,
      venues_here: [{ code: "L9", name: "Roadside Shrine", kind: "", hours: "" }],
    },
  });
  if (/venueClosed/.test(el.innerHTML)) failures.push("venue with unknown hours reported as closed");
  if (!el.innerHTML.includes("Roadside Shrine")) failures.push("hourless venue not listed");

  // 6. Names are escaped, not injected.
  sandbox.updateVenueLine({
    current_location: {
      name: "X", inside_venue: false,
      venues_here: [{ code: "L4", name: '<img src=x onerror=alert(1)>', kind: "", open: true, hours: "" }],
    },
  });
  if (el.innerHTML.includes("<img")) failures.push("venue name was not HTML-escaped");

  if (failures.length) {
    console.error("FAIL");
    for (const f of failures) console.error("  -", f);
    return 1;
  }
  console.log("PASS  venues render, closed state shows, keeper and exit appear");
  return 0;
}

process.exit(main());
