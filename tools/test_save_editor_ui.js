/**
 * The browser save editor, where it decides things on its own.
 *
 * The API refuses a bad edit, but by then the request has already been aimed.
 * Three decisions are made in the page before anything is sent, and each one
 * can be wrong in a way the server cannot see:
 *
 *   1. Which row an edit points at. The API applies a `set` to every row its
 *      `where` matches, so a clause that fits two rows changes the wrong one
 *      and reports success. Rows with nothing unique about them must come back
 *      as null and be shown read-only, not guessed at.
 *   2. What type a value keeps. Every field in the grid hands back a string,
 *      and writing "1" where the save held 1 turns a number column into
 *      strings one edit at a time -- silently, since the API takes any scalar.
 *   3. What the confirm dialog says. It is built from the server's own dry run
 *      rather than from what the page believes, so the number in the dialog is
 *      the number that lands, and cancelling writes nothing.
 *
 * Exit 0 = all three hold
 * Exit 1 = one regressed
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
  const asyncStart = source.indexOf(`\nasync function ${name}(`);
  const from = start >= 0 ? start : asyncStart;
  if (from < 0) throw new Error(`function ${name} not found in app.js`);
  let i = source.indexOf("{", from);
  let depth = 0;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(from, i + 1);
    }
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

function extractConst(source, name) {
  const start = source.indexOf(`\nconst ${name} = `);
  if (start < 0) throw new Error(`const ${name} not found in app.js`);
  const lineEnd = source.indexOf("\n", start + 1);
  const firstLine = source.slice(start, lineEnd);
  if (/;\s*$/.test(firstLine)) return firstLine;
  let i = source.indexOf("=", start);
  let depth = 0;
  let started = false;
  for (; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{" || ch === "[") {
      depth += 1;
      started = true;
    } else if (ch === "}" || ch === "]") {
      depth -= 1;
      if (started && depth === 0) return source.slice(start, i + 2);
    }
  }
  throw new Error(`unbalanced brackets extracting ${name}`);
}

let source;
try {
  source = fs.readFileSync(APP_JS, "utf8");
} catch (error) {
  console.log(`cannot read static/app.js -- ${error.message}`);
  process.exit(2);
}

let failures = 0;
function check(label, ok, detail) {
  if (ok) return;
  failures += 1;
  console.log(`  FAIL ${label}${detail ? ` -- ${detail}` : ""}`);
}

function same(label, got, want) {
  check(label, JSON.stringify(got) === JSON.stringify(want), `want ${JSON.stringify(want)}, got ${JSON.stringify(got)}`);
}

// The page under test, minus its browser. Anything the editor reaches for that
// only a browser can give is stubbed here, so a stray dependency shows up as a
// harness error rather than passing quietly.
const calls = { fetch: [], status: [], confirms: [] };
const sandbox = {
  console,
  JSON,
  Number,
  String,
  Object,
  Array,
  Set,
  Map,
  encodeURIComponent,
  fetchResponses: [],
  calls,
};
sandbox.window = { confirm: () => true };
sandbox.document = { querySelector: () => null, querySelectorAll: () => [] };
sandbox.fetch = async (url, options) => {
  const body = options?.body ? JSON.parse(options.body) : null;
  calls.fetch.push({ url, method: options?.method || "GET", body });
  const next = sandbox.fetchResponses.shift();
  if (!next) throw new Error(`no stubbed response for ${url}`);
  return { ok: next.ok !== false, status: next.status || 200, json: async () => next.json };
};
vm.createContext(sandbox);

let script;
try {
  script = [
    extractConst(source, "SAVE_EDITOR_ID_COLUMNS"),
    extractConst(source, "SAVE_EDITOR_LONG_VALUE"),
    extractFunction(source, "clipText"),
    extractFunction(source, "saveEditorIsScalar"),
    extractFunction(source, "saveEditorRowWhere"),
    extractFunction(source, "saveEditorVisibleRows"),
    extractConst(source, "SAVE_EDITOR_MIN_COLUMN"),
    extractConst(source, "SAVE_EDITOR_MAX_DEFAULT_COLUMN"),
    extractFunction(source, "saveEditorDefaultWidth"),
    extractFunction(source, "saveEditorCoerce"),
    extractFunction(source, "saveEditorBuildEdits"),
    extractFunction(source, "saveEditorChangeLines"),
    extractFunction(source, "postSaveEdits"),
    extractFunction(source, "saveEditorRunPreview"),
    extractFunction(source, "fetchSaveEditorData"),
    extractFunction(source, "saveEditorApply"),
    // Module-level state the extracted functions read and write. `var` so the
    // harness can reach it back out of the script's lexical scope.
    "var saveEditorSlot = 'Kael_Veyra';",
    "var saveEditorEdits = [];",
    "var saveEditorInvalid = new Set();",
    "var saveEditorData = null;",
    "var saveEditorTable = '';",
    "var saveEditorApplied = '';",
    "var saveBrowserSlots = [];",
    "function escapeHtml(v) { return String(v ?? ''); }",
    "function setSaveBrowserStatus(m, k) { calls.status.push([m, k || '']); }",
    "function renderSaveEditor() {}",
    "function renderSaveEditorQueue() {}",
    "this.api = {",
    "  rowWhere: saveEditorRowWhere,",
    "  visible: saveEditorVisibleRows,",
    "  defaultWidth: saveEditorDefaultWidth,",
    "  maxDefault: () => SAVE_EDITOR_MAX_DEFAULT_COLUMN,",
    "  coerce: saveEditorCoerce,",
    "  build: saveEditorBuildEdits,",
    "  lines: saveEditorChangeLines,",
    "  apply: saveEditorApply,",
    "  queue: (list) => { saveEditorEdits = list; },",
    "  readQueue: () => saveEditorEdits,",
    "  readApplied: () => saveEditorApplied,",
    "  clearApplied: () => { saveEditorApplied = ''; },",
    "};",
  ].join("\n\n");
  vm.runInContext(script, sandbox);
} catch (error) {
  console.log(`cannot load the editor out of app.js -- ${error.message}`);
  process.exit(2);
}

const api = sandbox.api;

// --- 1. which row an edit points at --------------------------------------
console.log("aiming an edit at one row");
{
  const rows = [
    { id: 1, code: "I1", name: "frayed sailor coat", quantity: 1 },
    { id: 2, code: "I4", name: "single seed in hand", quantity: 3 },
  ];
  same("a unique id is enough", api.rowWhere(rows[1], rows), { id: 2 });
}
{
  // Exports do not always carry a row id, and campaign merges have produced
  // repeats before.
  const rows = [
    { id: 1, code: "I1", name: "rope" },
    { id: 1, code: "I7", name: "rope" },
  ];
  same("a repeated id falls through to code", api.rowWhere(rows[1], rows), { code: "I7" });
}
{
  const rows = [
    { slot: "a", value: "1" },
    { slot: "b", value: "2" },
  ];
  same("no preferred column, so the whole row identifies it", api.rowWhere(rows[0], rows), {
    slot: "a",
    value: "1",
  });
}
{
  // The one that matters: two rows the same in every column. Any clause that
  // matches one matches both, and the API would set both and call it a
  // success. Read-only is the only honest answer.
  const rows = [
    { name: "torch", quantity: 1 },
    { name: "torch", quantity: 1 },
  ];
  check("identical rows are refused rather than guessed at", api.rowWhere(rows[0], rows) === null,
    JSON.stringify(api.rowWhere(rows[0], rows)));
}
{
  const long = "x".repeat(400);
  const rows = [
    { text: long, turn: 1 },
    { text: long, turn: 2 },
  ];
  const where = api.rowWhere(rows[0], rows);
  check("a long column is left out of the clause", where && !("text" in where), JSON.stringify(where));
  check("and the clause still lands on one row", where !== null);
}
{
  const rows = [{ id: 1, tags: ["a"], name: "rope" }];
  const where = api.rowWhere(rows[0], rows);
  same("a nested value never ends up in a where clause", where, { id: 1 });
}

// --- 1b. filtering must not move the target ------------------------------
console.log("filtering rows without moving the target");
{
  const rows = [
    { id: 1, code: "I1", name: "frayed sailor coat" },
    { id: 2, code: "I4", name: "single seed in hand" },
    { id: 3, code: "I7", name: "seed pouch" },
  ];
  same("everything is visible with no filter", api.visible(rows, "").map((e) => e.index), [0, 1, 2]);
  // The index is what an edit is queued against. If filtering renumbered the
  // rows, editing the first row on screen would write to the first row of the
  // table -- a different item.
  same("a filtered row keeps its place in the table", api.visible(rows, "seed").map((e) => e.index), [1, 2]);
  same("the match is case-blind", api.visible(rows, "SEED").map((e) => e.index), [1, 2]);
  same("any column can match", api.visible(rows, "I4").map((e) => e.index), [1]);
  same("no match is an empty list, not everything", api.visible(rows, "zzz").map((e) => e.index), []);
  check("a row with a null column does not blow up the filter", api.visible([{ id: 1, note: null }], "1").length === 1);
}

// --- 1c. starting column widths ------------------------------------------
console.log("choosing a column's starting width");
{
  const rows = [
    { id: 1, name: "threadbare scarf", description: "Starting gear (this_life_worn): ordinary threadbare scarf." },
    { id: 2, name: "frayed leather satchel", description: "Starting gear (this_life_common): a satchel." },
  ];
  const id = api.defaultWidth("id", rows);
  const name = api.defaultWidth("name", rows);
  const description = api.defaultWidth("description", rows);
  check("a short column stays narrow", id === 84, String(id));
  check("a name column fits its longest name", name > id && name < 260, String(name));
  check("a paragraph column is capped, not unbounded", description === api.maxDefault(), String(description));
  check("wider content means a wider column", name > id);
  check("the header alone sets a floor for an empty column", api.defaultWidth("enchantments", []) >= 84);
}
{
  // model_logs runs to thousands of rows. Scanning every one of them to pick a
  // width would be paid on every render, including every keystroke in the
  // filter box.
  const many = Array.from({ length: 500 }, (_, i) => ({ note: i < 60 ? "short" : "x".repeat(300) }));
  const width = api.defaultWidth("note", many);
  check("only the first rows are sampled", width < 120, `${width}px — it read past row 60`);
}

// --- 2. what type a value keeps ------------------------------------------
console.log("keeping a column's type");
{
  same("a number typed into a text box stays a number", api.coerce(3, "1"), { value: 1 });
  same("and a decimal survives", api.coerce(1.5, "2.25"), { value: 2.25 });
  check("words in a number field are refused", Boolean(api.coerce(3, "lots").error), JSON.stringify(api.coerce(3, "lots")));
  check("and so is an emptied number field", Boolean(api.coerce(3, "").error));
  same("true stays a boolean", api.coerce(false, "true"), { value: true });
  same("and 0 reads as false", api.coerce(true, "0"), { value: false });
  check("nonsense in a boolean field is refused", Boolean(api.coerce(true, "maybe").error));
  same("text stays text", api.coerce("rope", "old rope"), { value: "old rope" });
  same("a number typed into a text column stays text", api.coerce("rope", "12"), { value: "12" });
  same("an emptied null column is still null", api.coerce(null, ""), { value: null });
  same("a filled null column becomes text", api.coerce(null, "hello"), { value: "hello" });
}

// --- 3. the queue becomes the request ------------------------------------
console.log("building the request");
{
  const where = { code: "I4" };
  const built = api.build([
    { op: "set", table: "inventory", where, column: "quantity", value: 1, before: 3 },
    { op: "set", table: "inventory", where, column: "name", value: "a seed", before: "seed" },
  ]);
  same("two columns on one row are one edit", built, [
    { table: "inventory", where, set: { quantity: 1, name: "a seed" } },
  ]);
}
{
  const where = { code: "I4" };
  const built = api.build([
    { op: "set", table: "inventory", where, column: "quantity", value: 1, before: 3 },
    { op: "delete", table: "inventory", where },
  ]);
  same("a delete drops the sets queued for that same row", built, [
    { table: "inventory", where, delete: true },
  ]);
}
{
  const built = api.build([
    { op: "set", table: "inventory", where: { code: "I4" }, column: "quantity", value: 1, before: 3 },
    { op: "delete", table: "inventory", where: { code: "I9" } },
  ]);
  check("a delete elsewhere leaves the set alone", built.length === 2 && built[0].set, JSON.stringify(built));
}
{
  const built = api.build([{ op: "insert", table: "inventory", values: { code: "I5", name: "rope" } }]);
  same("an insert passes through", built, [{ table: "inventory", insert: { code: "I5", name: "rope" } }]);
}
{
  const built = api.build([
    { op: "set", table: "inventory", where: { code: "I4" }, column: "quantity", value: 1, before: 3 },
    { op: "set", table: "player", where: { id: 1 }, column: "gold", value: 40, before: 14 },
  ]);
  check("different tables stay separate edits", built.length === 2, JSON.stringify(built));
}
{
  const lines = api.lines([
    { op: "set", table: "inventory", where: { code: "I4" }, column: "quantity", value: 1, before: 3 },
  ]);
  check("a queued change reads as a sentence", /quantity: 3 → 1/.test(lines[0]), lines[0]);
}

// --- 4. the confirm dialog is the server's count, and cancel writes nothing
console.log("confirming before writing");

const SAVE = {
  slot: "Kael_Veyra",
  metadata: { player_name: "Kael Veyra", turn: 2 },
  tables: { inventory: [{ id: 2, code: "I4", name: "single seed in hand", quantity: 3 }] },
  columns: { inventory: ["id", "code", "name", "quantity"] },
  blocked: [],
};

function reset() {
  calls.fetch.length = 0;
  calls.status.length = 0;
  calls.confirms.length = 0;
  sandbox.fetchResponses.length = 0;
  api.clearApplied();
  api.queue([{ op: "set", table: "inventory", where: { code: "I4" }, column: "quantity", value: 1, before: 3 }]);
}

/** Assertions must survive a broken editor: a crash here hides the verdict. */
function bodyOf(index) {
  return calls.fetch[index] ? calls.fetch[index].body || {} : {};
}

/**
 * A throw is a result too. Letting one out of apply() would abandon the checks
 * that come after it and report a harness fault instead of a failure.
 */
async function runApply() {
  try {
    await api.apply();
    return "";
  } catch (error) {
    return error.message || String(error);
  }
}

(async () => {
  // The page thinks one row changes. The server says two. The dialog must say
  // two -- the page's guess never reaches the user.
  reset();
  sandbox.window.confirm = (text) => {
    calls.confirms.push(text);
    return false;
  };
  sandbox.fetchResponses.push({ json: { dry_run: true, rows_changed: 2, edits: [] } });
  await runApply();
  check("a dry run is sent first", bodyOf(0).dry_run === true, JSON.stringify(bodyOf(0)));
  check("the dialog quotes the server's count", /Apply 2 changes/.test(calls.confirms[0] || ""), calls.confirms[0]);
  check("cancelling writes nothing", calls.fetch.length === 1, `${calls.fetch.length} requests`);
  check("and the queue survives the cancel", api.readQueue().length === 1);

  // Nothing to do: the value is already what was typed. No dialog, no write.
  reset();
  calls.confirms.length = 0;
  sandbox.fetchResponses.push({ json: { dry_run: true, rows_changed: 0, edits: [] } });
  await runApply();
  check("a no-op is not offered as a change", calls.confirms.length === 0);
  check("and nothing is written for it", calls.fetch.length === 1, `${calls.fetch.length} requests`);

  // Accepted: dry run, then the write, then a re-read so the grid shows the
  // file rather than the queue.
  reset();
  sandbox.window.confirm = () => true;
  sandbox.fetchResponses.push({ json: { dry_run: true, rows_changed: 1, edits: [] } });
  sandbox.fetchResponses.push({ json: { rows_changed: 1, backup: "world.json.bak-20260828-045637" } });
  sandbox.fetchResponses.push({ json: SAVE });
  await runApply();
  check("the write follows the dry run", bodyOf(1).dry_run === false, JSON.stringify(bodyOf(1)));
  check(
    "the write carries the same edits",
    calls.fetch.length >= 2 && JSON.stringify(bodyOf(0).edits) === JSON.stringify(bodyOf(1).edits),
    `${JSON.stringify(bodyOf(0).edits)} vs ${JSON.stringify(bodyOf(1).edits)}`,
  );
  check("the queue is emptied once it is on disk", api.readQueue().length === 0);
  const last = calls.status[calls.status.length - 1] || [];
  check("the backup filename is reported back", /world\.json\.bak-/.test(last[0] || ""), last[0]);

  // A refusal at the dry run must not leave the queue looking applied.
  reset();
  sandbox.fetchResponses.push({
    ok: false,
    status: 400,
    json: { detail: "Edit 0: nothing in 'inventory' matches {\"code\": \"I99\"}." },
  });
  let raised = await runApply();
  check("a refusal is raised, not swallowed", /nothing in 'inventory' matches/.test(raised), raised);
  check("and the queue is kept so it can be fixed", api.readQueue().length === 1);

  // The dry run passes and the write is refused anyway -- a slot deleted from
  // another tab, a disk that filled up. The queue is the only copy of the work
  // at that moment, so it must still be there.
  reset();
  sandbox.fetchResponses.push({ json: { dry_run: true, rows_changed: 1, edits: [] } });
  sandbox.fetchResponses.push({ ok: false, status: 404, json: { detail: "Save 'Kael_Veyra' was not found." } });
  raised = await runApply();
  check("a refused write is raised", /was not found/.test(raised), raised);
  check("the queue survives a refused write", api.readQueue().length === 1, `${api.readQueue().length} left`);
  check("and nothing offers to load a save that was never written", api.readApplied() === "", api.readApplied());

  if (failures) {
    console.log(`\n${failures} failure(s)`);
    process.exit(1);
  }
  console.log("\nthe editor aims, types and confirms correctly");
  process.exit(0);
})().catch((error) => {
  console.log(`harness error -- ${error.stack || error.message}`);
  process.exit(2);
});
