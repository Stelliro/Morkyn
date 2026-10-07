/**
 * Regression: the read-aloud helpers in static/app.js (TODO n24).
 *
 * The narration is spoken paragraph by paragraph. What reaches the speech
 * route must be the shipped prose only: no [[codes]], no bare L1/I2 codes,
 * no HTML or markdown marks. The Play bar under the narration is rebuilt on
 * every render from a small view object, and every string in it goes through
 * escapeHtml. These are pure functions, so they run here under `vm` without a
 * browser; `speechItems` in ui/interact.js needs the DOM and is only
 * syntax-checked, together with app.js.
 *
 * Exit 0 = all cases pass
 * Exit 1 = a case regressed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");
const INTERACT_JS = path.join(ROOT, "static", "ui", "interact.js");

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

/** A top-level `const NAME = <literal>;` line, so the helpers see their limits. */
function extractConst(source, name) {
  const match = source.match(new RegExp(`\\nconst ${name} = [^\\n]*;`));
  if (!match) throw new Error(`const ${name} not found in app.js`);
  return match[0];
}

function buildSandbox() {
  const source = fs.readFileSync(APP_JS, "utf8");
  const code = [
    extractConst(source, "TTS_MAX_PARAGRAPHS"),
    extractConst(source, "TTS_MAX_PARAGRAPH_CHARS"),
    extractFunction(source, "escapeHtml"),
    extractFunction(source, "ttsClientClean"),
    extractFunction(source, "ttsClientParagraphs"),
    extractFunction(source, "ttsPlayBarHtml"),
  ].join("\n\n");
  const sandbox = { console };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox;
}

function syntaxCheck(file) {
  const result = spawnSync(process.execPath, ["--check", file], { encoding: "utf8" });
  return result.status === 0 ? "" : (result.stderr || result.stdout || `exit ${result.status}`).trim();
}

function main() {
  let sb;
  try {
    sb = buildSandbox();
  } catch (err) {
    console.error("harness error:", err.message);
    return 2;
  }
  const failures = [];
  const check = (cond, message) => { if (!cond) failures.push(message); };

  // 1. Cleaning: codes and markup go, prose and names stay.
  const dirty = "The gate at [[L1]] creaks. **Mira** [[A]] looks up; N12 and L3 are gone. <b>Run</b> &amp; hide, I said. See [the map](https://example.org/map).";
  const clean = sb.ttsClientClean(dirty);
  check(!/\[\[/.test(clean), `[[codes]] not stripped: ${clean}`);
  check(!/\bN12\b|\bL3\b|\bL1\b/.test(clean), `bare codes not stripped: ${clean}`);
  check(!/<|>/.test(clean) || /& hide/.test(clean), `HTML not stripped: ${clean}`);
  check(!clean.includes("**"), `bold marks kept: ${clean}`);
  check(!/https?:/.test(clean), `URL kept: ${clean}`);
  check(clean.includes("the map"), `link label lost: ${clean}`);
  check(clean.includes("Mira") && clean.includes("creaks") && clean.includes("& hide, I said."), `prose lost: ${clean}`);
  check(!/ {2,}/.test(clean), `spaces not collapsed: ${JSON.stringify(clean)}`);
  check(sb.ttsClientClean("[[L1]] [[A]] I2") === "", "code-only input should clean to an empty string");
  check(sb.ttsClientClean("I went to the door. NO! Not again.") === "I went to the door. NO! Not again.", "plain prose with an all-caps word was altered");
  check(sb.ttsClientClean("# Heading\n> quoted\n- item one\n1. item two") === "Heading\nquoted\nitem one\nitem two", `markdown line marks: ${JSON.stringify(sb.ttsClientClean("# Heading\n> quoted\n- item one\n1. item two"))}`);
  check(sb.ttsClientClean("Don't stop; it's fine.") === "Don't stop; it's fine.", "apostrophes were altered");

  // 2. Paragraphs: single and double newlines split, empties drop, capped at 60.
  const paras = sb.ttsClientParagraphs("First line.\n\nSecond line.\nThird line.\n   \n[[L1]]\nFourth.");
  check(paras.length === 4, `expected 4 paragraphs, got ${paras.length}: ${JSON.stringify(paras)}`);
  check(paras[0] === "First line." && paras[3] === "Fourth.", `paragraph order or trim wrong: ${JSON.stringify(paras)}`);
  check(sb.ttsClientParagraphs("").length === 0, "empty text should give no paragraphs");
  check(sb.ttsClientParagraphs("   \n\n  ").length === 0, "blank text should give no paragraphs");
  const many = sb.ttsClientParagraphs(Array.from({ length: 80 }, (_, i) => `Paragraph ${i + 1}.`).join("\n"));
  check(many.length === 60, `cap at 60 paragraphs, got ${many.length}`);
  const sentence = "The lantern swings and the shadows lean away from it, one by one, until the hall is bare. ";
  const longLine = sentence.repeat(60).trim(); // ~5400 chars, over the speak route's 4000
  const split = sb.ttsClientParagraphs(longLine);
  check(split.length >= 2, `an overlong paragraph should be split, got ${split.length}`);
  check(split.every((p) => p.length <= 4000), "a split piece is still over 4000 characters");
  check(split.every((p) => /[.!?]$/.test(p)), `split pieces should end at a sentence: ${JSON.stringify(split.map((p) => p.slice(-20)))}`);
  check(split.join(" ") === longLine, "splitting lost or reordered text");

  // 3. The Play bar: idle.
  const idle = sb.ttsPlayBarHtml({ playing: false });
  check(idle.includes('data-tts-action="play"'), "idle bar has no Play action");
  check(/data-tts-action="stop"[^>]*\bhidden\b/.test(idle), "idle bar should hide Stop");
  check(idle.includes(">Play<"), "idle bar label should read Play");
  // 4. Playing: Pause, visible Stop, paragraph counter.
  const playing = sb.ttsPlayBarHtml({ playing: true, index: 2, total: 6 });
  check(playing.includes('data-tts-action="pause"'), "playing bar has no Pause action");
  check(!/data-tts-action="stop"[^>]*\bhidden\b/.test(playing) && playing.includes('data-tts-action="stop"'), "playing bar should show Stop");
  check(playing.includes("Paragraph 2 of 6"), `playing bar lacks the counter: ${playing}`);
  // 5. Paused: Resume.
  const paused = sb.ttsPlayBarHtml({ paused: true, index: 3, total: 6 });
  check(paused.includes('data-tts-action="resume"') && paused.includes(">Resume<"), "paused bar has no Resume action");
  check(!/data-tts-action="stop"[^>]*\bhidden\b/.test(paused), "paused bar should show Stop");
  // 6. Status text passes through; errors are escaped.
  const synth = sb.ttsPlayBarHtml({ playing: true, index: 1, total: 3, text: "Synthesizing…" });
  check(synth.includes("Synthesizing…"), "status text not rendered");
  const evil = sb.ttsPlayBarHtml({ playing: false, error: 'Paragraph 3 could not be read: <img src=x onerror="alert(1)">' });
  check(!evil.includes("<img"), "error text was inserted as HTML");
  check(evil.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"), `error text not escaped: ${evil}`);
  check(evil.includes('class="ttsStatus bad"'), "error status should carry the bad class");
  // 7. Empty status span when there is nothing to say (no layout text).
  const quiet = sb.ttsPlayBarHtml({ playing: false, text: "" });
  check(/<span class="ttsStatus" aria-live="polite"><\/span>/.test(quiet), `idle status should be empty: ${quiet}`);
  check(sb.ttsPlayBarHtml(undefined).includes('data-tts-action="play"'), "a missing view should still render an idle bar");

  // 8. Both scripts parse.
  for (const file of [APP_JS, INTERACT_JS]) {
    const err = syntaxCheck(file);
    if (err) failures.push(`node --check ${path.relative(ROOT, file)}: ${err}`);
  }
  // 9. The context-menu side exists and is exported for the console.
  const interact = fs.readFileSync(INTERACT_JS, "utf8");
  check(interact.includes("function speechItems(event)"), "interact.js lacks speechItems");
  check(/window\.MorkynInteract = \{[^}]*\bspeechItems\b/.test(interact), "speechItems is not exported on window.MorkynInteract");
  check(interact.includes('"Play selected text"') && interact.includes('"Play this paragraph"'), "menu item labels changed");
  check(interact.includes('form: ".ttsForm"'), "PROVIDER_FORMS lacks the speech form entry");

  if (failures.length) {
    console.error(`test_tts_ui: ${failures.length} failure(s)`);
    for (const f of failures) console.error(` - ${f}`);
    return 1;
  }
  console.log("test_tts_ui: ok");
  return 0;
}

process.exitCode = main();
