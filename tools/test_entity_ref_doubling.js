/**
 * Regression: "Name [[CODE]]" must render as ONE clickable reference.
 *
 * The server appends the code after the name on purpose
 * (`_inject_entity_codes_for_known_names` in app/llm.py writes
 * "Low Gate Timber Arch [[L1]]"). linkifyText used to expand the [[code]] into
 * a labelled button AND separately linkify the bare name sitting beside it, so
 * every reference rendered twice:
 *
 *     Ash Road Cut Ash Road Cut comes into focus ...
 *     What you still carry is plain: soft shoes soft shoes, and zip hoodie zip hoodie.
 *
 * The narration below is the real stored opening from a playthrough
 * (journal row, turn 1), not a synthetic string.
 *
 * Exit 0 = each entity renders exactly once
 * Exit 1 = doubling present
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

/** Pull a top-level `function name(...) { ... }` out of app.js by brace matching. */
function extractFunction(source, name) {
  const start = source.indexOf(`\nfunction ${name}(`);
  if (start < 0) throw new Error(`function ${name} not found in app.js`);
  let i = source.indexOf("{", start);
  if (i < 0) throw new Error(`no body for ${name}`);
  let depth = 0;
  let inString = null;
  let inLineComment = false;
  let inBlockComment = false;
  let inRegex = false;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    const prev = source[i - 1];
    const next = source[i + 1];
    if (inLineComment) {
      if (ch === "\n") inLineComment = false;
      continue;
    }
    if (inBlockComment) {
      if (ch === "*" && next === "/") { inBlockComment = false; i += 1; }
      continue;
    }
    if (inString) {
      if (ch === "\\") { i += 1; continue; }
      if (ch === inString) inString = null;
      continue;
    }
    if (inRegex) {
      if (ch === "\\") { i += 1; continue; }
      if (ch === "[") { // character class can contain an unescaped /
        while (i < source.length && source[i] !== "]") {
          if (source[i] === "\\") i += 1;
          i += 1;
        }
        continue;
      }
      if (ch === "/") inRegex = false;
      continue;
    }
    if (ch === "/" && next === "/") { inLineComment = true; i += 1; continue; }
    if (ch === "/" && next === "*") { inBlockComment = true; i += 1; continue; }
    if (ch === '"' || ch === "'" || ch === "`") { inString = ch; continue; }
    if (ch === "/" && /[(,=:[!&|?{};\n]/.test(String(prev || "").trim() || prev || "\n")) {
      inRegex = true;
      continue;
    }
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`unbalanced braces while extracting ${name}`);
}

function buildSandbox() {
  const source = fs.readFileSync(APP_JS, "utf8");
  const needed = [
    "escapeHtml",
    "escapeRegExp",
    "entityLabel",
    "getEntityMap",
    "stripLeakedEntityHtml",
    "linkifyKnownEntityNames",
    "linkifyText",
  ];
  const chunks = needed.map((n) => extractFunction(source, n));
  // The fix under test. On a pre-fix app.js it is simply absent, so stub it as
  // identity — that reproduces the old rendering and lets this file fail with a
  // real doubling report instead of a harness error.
  try {
    chunks.push(extractFunction(source, "collapseNameCodePairs"));
  } catch {
    chunks.push("function collapseNameCodePairs(text) { return String(text ?? ''); }");
  }
  const code = chunks.join("\n\n");
  const sandbox = { state: null, PREFIX: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox;
}

// Real world state from the playthrough that produced the screenshot.
const STATE = {
  current_location: { code: "L1", name: "Ash Road Cut" },
  locations: [{ code: "L1", name: "Ash Road Cut", npcs: [], events: [] }],
  inventory: [
    { code: "I1", name: "soft shoes" },
    { code: "I2", name: "zip hoodie" },
  ],
  events: [],
  npcs: [],
};

// Verbatim from the journal (kind='narration', turn 1), trimmed to the lines under test.
const NARRATION = [
  "Ash Road Cut [[L1]] comes into focus without waiting for a command.",
  "What you still carry is plain: soft shoes [[I1]], and zip hoodie [[I2]].",
  "[ STATUS ] Location: Ash Road Cut [[L1]]",
].join("\n");

function countOccurrences(haystack, needle) {
  let n = 0;
  let at = 0;
  for (;;) {
    const found = haystack.indexOf(needle, at);
    if (found < 0) return n;
    n += 1;
    at = found + needle.length;
  }
}

function main() {
  let sandbox;
  try {
    sandbox = buildSandbox();
  } catch (err) {
    console.error("harness error:", err.message);
    return 2;
  }
  sandbox.state = STATE;

  const failures = [];

  // 1. Each name appears exactly as many times as its code does — never doubled.
  const html = sandbox.linkifyText(NARRATION);
  const expected = { "Ash Road Cut": 2, "soft shoes": 1, "zip hoodie": 1 };
  for (const [label, want] of Object.entries(expected)) {
    const got = countOccurrences(html, label);
    if (got !== want) failures.push(`"${label}" rendered ${got}x, expected ${want}x`);
  }

  // 2. No two identical labels sit adjacent (the visible symptom).
  for (const label of Object.keys(expected)) {
    const doubled = new RegExp(`${label}\\s*(<[^>]*>\\s*)*${label}`, "i");
    if (doubled.test(html)) failures.push(`"${label}" still renders back-to-back`);
  }

  // 3. Every reference is still clickable — the fix must not drop the link.
  for (const code of ["L1", "I1", "I2"]) {
    if (!html.includes(`data-code="${code}"`)) failures.push(`${code} lost its entity button`);
  }

  // 4. A name NOT followed by its own code still linkifies (existing behaviour).
  const bare = sandbox.linkifyText("The road out of Ash Road Cut was quiet.");
  if (!bare.includes('data-code="L1"')) failures.push("bare name no longer linkifies");
  if (countOccurrences(bare, "Ash Road Cut") !== 1) failures.push("bare name doubled");

  // 5. A name followed by a DIFFERENT entity's code must not be swallowed.
  const mixed = sandbox.linkifyText("soft shoes [[L1]] sat by the door.");
  if (!mixed.includes("soft shoes")) failures.push("unrelated name was eaten by the collapse");
  if (!mixed.includes("Ash Road Cut")) failures.push("unrelated code lost its label");

  // 6. Unknown codes stay readable rather than vanishing.
  const unknown = sandbox.linkifyText("A door marked [[L9]] stood shut.");
  if (!unknown.includes("L9")) failures.push("unknown code disappeared");

  if (failures.length) {
    console.error("FAIL");
    for (const f of failures) console.error("  -", f);
    console.error("\nrendered:\n" + html);
    return 1;
  }

  console.log("PASS  entity references render exactly once and stay clickable");
  console.log("  " + html.split("\n")[0]);
  return 0;
}

process.exit(main());
