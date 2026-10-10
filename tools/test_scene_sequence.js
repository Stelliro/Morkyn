/**
 * Tests for static/ui/scene_sequence.js (TODO g17, built but not wired).
 *
 * The sequencer owns the order of what reaches the narration area: one scene
 * streams at a time, ambient lines wait for the stream, stale ones are
 * dropped. It is pure (callbacks in, events out), so it runs here under node
 * with `global.window = {}`, no document, and fake timers injected.
 *
 * Exit 0 = all cases pass
 * Exit 1 = a case regressed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const MODULE = path.join(ROOT, "static", "ui", "scene_sequence.js");
const MODULE_NAME = "scene_sequence";

/* ------------------------------------------------------------------------
   Harness
   ------------------------------------------------------------------------ */

function assert(cond, message) {
  if (!cond) throw new Error(message || "assertion failed");
}

function assertEqual(actual, expected, message) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${message || "values differ"}: got ${a}, want ${e}`);
}

function assertThrows(fn, message) {
  let threw = false;
  try {
    fn();
  } catch (_) {
    threw = true;
  }
  if (!threw) throw new Error(message || "expected a throw");
}

// Deterministic timers: nothing fires until advance(ms) is called.
function makeTimers() {
  let clock = 0;
  let nextId = 0;
  const pending = new Map();
  return {
    setTimeout(fn, ms) {
      nextId += 1;
      pending.set(nextId, { at: clock + Number(ms || 0), fn });
      return nextId;
    },
    clearTimeout(id) {
      pending.delete(id);
    },
    advance(ms) {
      clock += ms;
      const due = [...pending.entries()].filter(([, t]) => t.at <= clock).sort((a, b) => a[1].at - b[1].at);
      due.forEach(([id, t]) => {
        pending.delete(id);
        t.fn();
      });
    },
    pendingCount() {
      return pending.size;
    },
    now() {
      return clock;
    },
  };
}

// A sequencer with fake timers, a recording log and every event recorded.
function harness(rules) {
  const timers = makeTimers();
  const logs = [];
  const events = [];
  const seq = window.MorkynSceneSequence.create({
    rules,
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
    now: timers.now,
    log: (...args) => logs.push(args),
  });
  window.MorkynSceneSequence.EVENTS.forEach((name) => {
    seq.on(name, (payload) => events.push({ event: name, payload }));
  });
  const named = (name) => events.filter((e) => e.event === name);
  return { seq, timers, logs, events, named };
}

// A scene whose render keeps done() for the test to call later.
function heldScene(seq, turn, label, finishNow) {
  const box = { done: null, rendered: 0 };
  box.id = seq.enqueueScene({
    token: { turn, step: "" },
    label,
    render: (done) => {
      box.rendered += 1;
      box.done = done;
    },
    finishNow,
  });
  return box;
}

function recordingShow() {
  const shown = [];
  return { shown, show: (text) => shown.push(text) };
}

function isInt(v) {
  return typeof v === "number" && Number.isInteger(v);
}

function assertTokenShape(token, message) {
  assertEqual(Object.keys(token).sort(), ["seq", "step", "turn"], `${message}: token keys`);
  assert(isInt(token.turn), `${message}: turn is an int`);
  assert(typeof token.step === "string", `${message}: step is a string`);
  assert(isInt(token.seq), `${message}: seq is an int`);
}

/* ------------------------------------------------------------------------
   Cases
   ------------------------------------------------------------------------ */

const CASES = [];
function test(name, fn) {
  CASES.push({ name, fn });
}

test("test_module_is_a_leaf", () => {
  const source = fs.readFileSync(MODULE, "utf8");
  const required = [
    "Status: built, not wired (TODO g17).",
    "Wiring (not done):",
    "Turn on:",
    "Tests: tools/test_scene_sequence.js",
  ];
  required.forEach((line) => assert(source.includes(line), `header line missing: ${line}`));
  // Nothing under app/ or static/ names the module or its export other than the file itself.
  const hits = [];
  const walk = (dir) => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__" || entry.name === "node_modules") return;
        walk(full);
        return;
      }
      if (!/\.(py|js|html|css|md|txt|json)$/.test(entry.name)) return;
      if (full === MODULE) return;
      const text = fs.readFileSync(full, "utf8");
      if (text.includes(MODULE_NAME) || text.includes("MorkynSceneSequence")) hits.push(path.relative(ROOT, full));
    });
  };
  walk(path.join(ROOT, "app"));
  walk(path.join(ROOT, "static"));
  assertEqual(hits, [], "files under app/ or static/ that name the module");
  ["index.html", "popout.html"].forEach((page) => {
    const text = fs.readFileSync(path.join(ROOT, "static", page), "utf8");
    assert(!text.includes("scene_sequence.js"), `static/${page} loads the module`);
  });
});

test("no_dom_touch", () => {
  // The module loaded with window = {} and no document (see main()); the
  // export object carries every method of the design.
  assert(typeof document === "undefined", "the harness must not define document");
  const api = window.MorkynSceneSequence;
  const methods = [
    "tokenOf",
    "compareTokens",
    "create",
    "enqueueScene",
    "beginScene",
    "endScene",
    "enqueueAmbient",
    "flush",
    "finishCurrent",
    "isBusy",
    "pending",
    "lastShown",
    "reset",
    "on",
  ];
  methods.forEach((m) => assert(typeof api[m] === "function", `export lacks ${m}()`));
  assert(api.RULES && typeof api.RULES === "object", "RULES missing");
  assertEqual(Object.keys(window).sort(), ["MorkynSceneSequence"], "the module set more than its one export on window");
});

test("rules_match_the_design_table", () => {
  const rules = window.MorkynSceneSequence.RULES;
  assertEqual(rules.ambientMax, 3, "ambientMax");
  assertEqual(rules.finishCurrentAt, 2, "finishCurrentAt");
  assertEqual(rules.watchdogMs, 15000, "watchdogMs");
  assertEqual(rules.staleRule, "turn_below_last_shown", "staleRule");
  assertEqual(rules.sameTurnAmbient, "show", "sameTurnAmbient");
  assertEqual(rules.idleAmbient, "immediate", "idleAmbient");
  assert(Object.isFrozen(rules), "RULES is frozen");
  assertEqual(
    window.MorkynSceneSequence.EVENTS.slice(),
    ["scene-start", "scene-done", "scene-queued", "scene-timeout", "scene-finished-early", "ambient-shown", "ambient-held", "ambient-dropped", "reset"],
    "event names",
  );
  assertEqual(window.MorkynSceneSequence.DROP_REASONS.slice(), ["stale", "overflow", "reset"], "drop reasons");
});

test("tokenOf_reads_turn_and_step", () => {
  const tokenOf = window.MorkynSceneSequence.tokenOf;
  assertEqual(tokenOf({ turn: 7, step: { to: [3, 4] } }), { turn: 7, step: "3,4", seq: 0 }, "turn and step");
  assertEqual(tokenOf({ state: { turn: 2 } }), { turn: 2, step: "", seq: 0 }, "state turn");
  assertEqual(tokenOf({}), { turn: 0, step: "", seq: 0 }, "empty payload");
  assertEqual(tokenOf(null), { turn: 0, step: "", seq: 0 }, "null payload");
  // A live turn payload: payload.turn is the narration object, the number is state.turn.
  assertEqual(tokenOf({ turn: { narration: "x" }, state: { turn: 9 } }), { turn: 9, step: "", seq: 0 }, "live payload");
  assertEqual(tokenOf({ travel: { to: [5, 6] } }).step, "5,6", "travel.to");
  assertEqual(tokenOf({ step: { to: { x: 1, y: 2 } } }).step, "1,2", "object target");
  assertEqual(tokenOf({ step: { to: "nowhere" } }).step, "", "bad target");
  assertEqual(tokenOf({ turn: "12" }).turn, 12, "numeric string turn");
  assertTokenShape(tokenOf({ turn: 3, step: { to: [1, 1] } }), "DisplayToken shape");
});

test("compareTokens_orders_by_turn_then_seq", () => {
  const cmp = window.MorkynSceneSequence.compareTokens;
  assertEqual(cmp({ turn: 1, seq: 9 }, { turn: 2, seq: 0 }), -1, "lower turn first");
  assertEqual(cmp({ turn: 2, seq: 0 }, { turn: 1, seq: 9 }), 1, "higher turn after");
  assertEqual(cmp({ turn: 2, seq: 1 }, { turn: 2, seq: 2 }), -1, "same turn, lower seq first");
  assertEqual(cmp({ turn: 2, seq: 2 }, { turn: 2, seq: 1 }), 1, "same turn, higher seq after");
  assertEqual(cmp({ turn: 2, seq: 2 }, { turn: 2, seq: 2 }), 0, "equal");
  assertEqual(cmp(null, {}), 0, "missing tokens compare as zero");
  const tokens = [{ turn: 3, seq: 1 }, { turn: 1, seq: 5 }, { turn: 3, seq: 0 }, { turn: 2, seq: 2 }];
  assertEqual(tokens.slice().sort(cmp), [{ turn: 1, seq: 5 }, { turn: 2, seq: 2 }, { turn: 3, seq: 0 }, { turn: 3, seq: 1 }], "sort");
});

test("idle_ambient_shows_immediately", () => {
  const h = harness();
  const rec = recordingShow();
  const id = h.seq.enqueueAmbient({ token: { turn: 1 }, text: " The road is quiet. ", show: rec.show });
  assert(id > 0, "returns an id");
  assertEqual(rec.shown, ["The road is quiet."], "shown synchronously, trimmed");
  assertEqual(h.named("ambient-shown").length, 1, "ambient-shown event");
  assertEqual(h.named("ambient-held").length, 0, "nothing held");
  assertTokenShape(h.named("ambient-shown")[0].payload.token, "ambient-shown token");
  assertEqual(h.named("ambient-shown")[0].payload.token.seq, 1, "seq assigned on enqueue");
  assertEqual(h.seq.enqueueAmbient({ token: { turn: 1 }, text: "   ", show: rec.show }), 0, "blank text returns 0");
  assertEqual(rec.shown.length, 1, "blank text shows nothing");
  assertThrows(() => h.seq.enqueueAmbient({ token: { turn: 1 }, text: "x" }), "show is required");
});

test("ambient_held_while_scene_in_flight_then_flushed", () => {
  const h = harness();
  const scene = heldScene(h.seq, 5, "turn");
  assertEqual(scene.rendered, 1, "render called at once when idle");
  assert(h.seq.isBusy(), "busy while in flight");
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 5 }, text: "First.", show: rec.show });
  h.seq.enqueueAmbient({ token: { turn: 5 }, text: "Second.", show: rec.show });
  assertEqual(rec.shown, [], "held while the scene streams");
  assertEqual(h.named("ambient-held").length, 2, "two ambient-held events");
  assertEqual(h.seq.pending(), { inFlight: { id: scene.id, label: "turn", token: { turn: 5, step: "", seq: 1 } }, scenes: 0, ambients: 2 }, "pending");
  assertEqual(h.seq.flush(), { shown: 0, dropped: 0 }, "flush while in flight shows nothing");
  assertEqual(rec.shown, [], "still held");
  scene.done();
  assertEqual(rec.shown, ["First.", "Second."], "shown once each, in order, after done()");
  assertEqual(h.named("scene-done").length, 1, "scene-done");
  assertEqual(h.named("scene-done")[0].payload.error, false, "no error");
  assert(!h.seq.isBusy(), "idle after done");
  assertEqual(h.seq.lastShown(), { turn: 5, step: "", seq: 1 }, "lastShown is the scene token");
  assertEqual(h.seq.pending(), { inFlight: null, scenes: 0, ambients: 0 }, "pending is empty");
});

test("stale_ambient_dropped", () => {
  const h = harness();
  const scene = heldScene(h.seq, 5, "turn");
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 4 }, text: "Old step.", show: rec.show });
  assertEqual(h.named("ambient-held").length, 1, "held first");
  scene.done();
  assertEqual(rec.shown, [], "stale line never shown");
  const dropped = h.named("ambient-dropped");
  assertEqual(dropped.length, 1, "one drop");
  assertEqual(dropped[0].payload.reason, "stale", "reason stale");
  assertEqual(dropped[0].payload.text, "Old step.", "which line");
});

test("same_turn_ambient_shown", () => {
  const h = harness();
  const scene = heldScene(h.seq, 5, "turn");
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 5 }, text: "Same turn.", show: rec.show });
  scene.done();
  assertEqual(rec.shown, ["Same turn."], "same-turn line shown on flush");
  assertEqual(h.named("ambient-dropped").length, 0, "nothing dropped");
  // A newer turn's ambient is shown too.
  const scene2 = heldScene(h.seq, 6, "turn");
  h.seq.enqueueAmbient({ token: { turn: 7 }, text: "Newer.", show: rec.show });
  scene2.done();
  assertEqual(rec.shown, ["Same turn.", "Newer."], "newer line shown");
});

test("overflow_drops_oldest", () => {
  const h = harness();
  const scene = heldScene(h.seq, 2, "turn");
  const rec = recordingShow();
  ["A", "B", "C", "D"].forEach((t) => h.seq.enqueueAmbient({ token: { turn: 2 }, text: t, show: rec.show }));
  const dropped = h.named("ambient-dropped");
  assertEqual(dropped.length, 1, "one overflow drop before flush");
  assertEqual(dropped[0].payload.reason, "overflow", "reason overflow");
  assertEqual(dropped[0].payload.text, "A", "the oldest went");
  assertEqual(h.seq.pending().ambients, 3, "three held (ambientMax)");
  scene.done();
  assertEqual(rec.shown, ["B", "C", "D"], "three shown in order");
});

test("second_scene_waits_for_first", () => {
  const h = harness();
  const first = heldScene(h.seq, 1, "first");
  const second = heldScene(h.seq, 2, "second");
  assertEqual(second.rendered, 0, "second render not called yet");
  assertEqual(h.named("scene-queued").length, 1, "scene-queued");
  assertEqual(h.named("scene-finished-early").length, 0, "one waiting scene does not finish the first");
  assertEqual(h.seq.pending().scenes, 1, "one waiting");
  first.done();
  assertEqual(second.rendered, 1, "second starts after first done");
  assertEqual(h.named("scene-start").map((e) => e.payload.label), ["first", "second"], "start order");
  second.done();
  assertEqual(h.seq.lastShown().turn, 2, "last shown is the second");
  assert(!h.seq.isBusy(), "idle at the end");
});

test("third_scene_finishes_current_early", () => {
  const h = harness();
  let finishCalls = 0;
  const first = heldScene(h.seq, 1, "wait", () => {
    finishCalls += 1;
    first.done(); // what streamTextToTargets' finishNow would do: full text, then onDone
  });
  const second = heldScene(h.seq, 2, "fight-1");
  assertEqual(finishCalls, 0, "a second scene only waits");
  const third = heldScene(h.seq, 3, "fight-2");
  assertEqual(finishCalls, 1, "third scene finishes the first at once");
  assertEqual(h.named("scene-finished-early").length, 1, "event scene-finished-early");
  assertEqual(h.named("scene-finished-early")[0].payload.label, "wait", "which scene");
  assertEqual(second.rendered, 1, "second started after the early finish");
  assertEqual(third.rendered, 0, "third still waits");
  second.done();
  assertEqual(third.rendered, 1, "third starts");
  third.done();
  assertEqual(finishCalls, 1, "finishNow called once in all");
});

test("finish_now_called_once_per_scene", () => {
  const h = harness();
  let finishCalls = 0;
  const first = heldScene(h.seq, 1, "a", () => {
    finishCalls += 1; // does not call done(): a finishNow that only clears the stream
  });
  heldScene(h.seq, 2, "b");
  heldScene(h.seq, 3, "c");
  heldScene(h.seq, 4, "d");
  assertEqual(finishCalls, 1, "a fourth scene does not call finishNow again");
  assertEqual(h.seq.finishCurrent(), false, "finishCurrent returns false once finishNow has been used");
  first.done();
  assertEqual(h.seq.pending().inFlight.label, "b", "b in flight");
  assertEqual(h.seq.finishCurrent(), false, "no finishNow on b");
});

test("finishCurrent_calls_in_flight_finishNow", () => {
  const h = harness();
  let calls = 0;
  heldScene(h.seq, 1, "a", () => {
    calls += 1;
  });
  assertEqual(h.seq.finishCurrent(), true, "returns true");
  assertEqual(calls, 1, "called");
  assertEqual(h.named("scene-finished-early").length, 1, "event");
  const idle = harness();
  assertEqual(idle.seq.finishCurrent(), false, "false when idle");
});

test("watchdog_ends_hung_scene", () => {
  const h = harness();
  heldScene(h.seq, 1, "hung");
  const next = heldScene(h.seq, 2, "next");
  assertEqual(h.timers.pendingCount(), 1, "watchdog armed");
  h.timers.advance(14999);
  assertEqual(next.rendered, 0, "not yet");
  h.timers.advance(2);
  assertEqual(h.named("scene-timeout").length, 1, "scene-timeout");
  assertEqual(h.named("scene-timeout")[0].payload.label, "hung", "the hung scene");
  assertEqual(h.named("scene-done")[0].payload.timeout, true, "scene-done carries timeout");
  assertEqual(next.rendered, 1, "next scene starts");
  assertEqual(h.seq.lastShown().turn, 1, "the hung scene still counts as shown");
  next.done();
  assertEqual(h.timers.pendingCount(), 0, "watchdog cleared on done");
  assertEqual(h.named("scene-timeout").length, 1, "no second timeout");
});

test("watchdog_is_cleared_by_done", () => {
  const h = harness();
  const scene = heldScene(h.seq, 1, "quick");
  scene.done();
  assertEqual(h.timers.pendingCount(), 0, "cleared");
  h.timers.advance(20000);
  assertEqual(h.named("scene-timeout").length, 0, "no timeout after done");
});

test("render_throw_does_not_wedge", () => {
  const h = harness();
  h.seq.enqueueScene({
    token: { turn: 1 },
    label: "broken",
    render: () => {
      throw new Error("boom");
    },
  });
  assertEqual(h.logs.length, 1, "log called");
  assertEqual(h.named("scene-done")[0].payload.error, true, "scene-done with error true");
  assert(!h.seq.isBusy(), "not wedged");
  const second = heldScene(h.seq, 2, "ok");
  assertEqual(second.rendered, 1, "second scene starts");
  second.done();
  // A throwing show() is caught as well.
  const h2 = harness();
  h2.seq.enqueueAmbient({
    token: { turn: 1 },
    text: "x",
    show: () => {
      throw new Error("show boom");
    },
  });
  assertEqual(h2.logs.length, 1, "show error logged");
  assertEqual(h2.named("ambient-shown").length, 1, "still counted as shown");
});

test("done_twice_ignored", () => {
  const h = harness();
  const scene = heldScene(h.seq, 1, "a");
  scene.done();
  scene.done();
  assertEqual(h.named("scene-done").length, 1, "one scene-done");
  assertEqual(h.logs.length, 0, "no log");
});

test("done_for_old_scene_ignored", () => {
  const h = harness();
  const first = heldScene(h.seq, 1, "a");
  const second = heldScene(h.seq, 2, "b");
  first.done();
  assertEqual(second.rendered, 1, "b in flight");
  first.done(); // stale callback from an earlier stream
  assertEqual(h.named("scene-done").length, 1, "b not ended by a's done");
  assertEqual(h.seq.pending().inFlight.label, "b", "b still in flight");
  second.done();
  assertEqual(h.named("scene-done").length, 2, "b ends on its own done");
});

test("reset_clears_everything", () => {
  const h = harness();
  heldScene(h.seq, 3, "a");
  heldScene(h.seq, 4, "b");
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 3 }, text: "held one", show: rec.show });
  h.seq.enqueueAmbient({ token: { turn: 3 }, text: "held two", show: rec.show });
  assertEqual(h.timers.pendingCount(), 1, "watchdog armed before reset");
  h.seq.reset();
  const dropped = h.named("ambient-dropped");
  assertEqual(dropped.map((e) => e.payload.reason), ["reset", "reset"], "held ambients dropped with reason reset");
  assertEqual(rec.shown, [], "nothing shown");
  assertEqual(h.seq.pending(), { inFlight: null, scenes: 0, ambients: 0 }, "pending zeros");
  assertEqual(h.seq.lastShown(), null, "lastShown cleared");
  assertEqual(h.timers.pendingCount(), 0, "watchdog cleared");
  assertEqual(h.named("reset").length, 1, "reset event");
  assertEqual(h.named("reset")[0].payload, { scenes: 2, ambients: 2 }, "reset summary");
  h.timers.advance(20000);
  assertEqual(h.named("scene-timeout").length, 0, "no timeout after reset");
  const after = heldScene(h.seq, 1, "fresh");
  assertEqual(after.rendered, 1, "usable after reset");
  after.done();
  // After reset lastShown is null, so a low-turn ambient is not stale.
  assertEqual(h.named("scene-done").length, 1, "scene-done after reset counts");
});

test("begin_end_pair_matches_enqueue", () => {
  const h = harness();
  const handle = h.seq.beginScene({ turn: 8 }, "self-rendered");
  assertEqual(Object.keys(handle).sort(), ["id", "label", "token"], "handle shape");
  assertTokenShape(handle.token, "handle token");
  assert(h.seq.isBusy(), "busy after beginScene");
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 8 }, text: "held", show: rec.show });
  assertEqual(rec.shown, [], "held during the self-rendered scene");
  assertEqual(h.seq.endScene({ id: handle.id + 100, label: "x", token: handle.token }), false, "wrong handle is refused");
  assertEqual(h.seq.endScene(null), false, "null handle is refused");
  assertEqual(rec.shown, [], "a refused endScene flushes nothing");
  assertEqual(h.seq.endScene(handle), true, "the right handle ends it");
  assertEqual(rec.shown, ["held"], "flushed on endScene");
  assertEqual(h.seq.endScene(handle), false, "ending twice returns false");
  assertEqual(h.seq.lastShown().turn, 8, "lastShown from the handle's token");
  // A beginScene while busy queues like enqueueScene does.
  const a = heldScene(h.seq, 9, "a");
  const queued = h.seq.beginScene({ turn: 10 }, "queued");
  assertEqual(h.seq.pending().scenes, 1, "queued behind a");
  assertEqual(h.seq.endScene(queued), false, "not in flight yet");
  a.done();
  assertEqual(h.seq.pending().inFlight.id, queued.id, "queued one now in flight");
  assertEqual(h.seq.endScene(queued), true, "ends once in flight");
});

test("enqueueScene_requires_render_and_assigns_seq", () => {
  const h = harness();
  assertThrows(() => h.seq.enqueueScene({ token: { turn: 1 } }), "render required");
  assertThrows(() => h.seq.enqueueScene(null), "null spec");
  const a = heldScene(h.seq, 1, "a");
  const b = heldScene(h.seq, 1, "b");
  const starts = h.named("scene-start");
  const queued = h.named("scene-queued");
  assertEqual(starts[0].payload.token.seq, 1, "first seq 1");
  assertEqual(queued[0].payload.token.seq, 2, "second seq 2");
  assert(a.id !== b.id, "distinct ids");
  assertEqual(h.seq.enqueueScene({ render: () => {} }) > b.id, true, "ids grow; token and label default");
  assertEqual(h.named("scene-queued")[1].payload.token, { turn: 0, step: "", seq: 3 }, "default token");
  assertEqual(h.named("scene-queued")[1].payload.label, "turn", "default label");
});

test("on_returns_unsubscribe_and_rejects_unknown_events", () => {
  const h = harness();
  let calls = 0;
  const off = h.seq.on("scene-start", () => {
    calls += 1;
  });
  heldScene(h.seq, 1, "a").done();
  assertEqual(calls, 1, "listener called");
  off();
  heldScene(h.seq, 2, "b").done();
  assertEqual(calls, 1, "unsubscribed");
  assertThrows(() => h.seq.on("no-such-event", () => {}), "unknown event rejected");
  assertThrows(() => h.seq.on("scene-start", "nope"), "non-function rejected");
  // A throwing listener is logged and does not stop the queue.
  h.seq.on("scene-done", () => {
    throw new Error("listener boom");
  });
  heldScene(h.seq, 3, "c").done();
  assert(h.logs.length >= 1, "listener error logged");
  assert(!h.seq.isBusy(), "queue still moves");
});

test("rules_override_through_create", () => {
  const h = harness({ ambientMax: 1, finishCurrentAt: 1, watchdogMs: 100 });
  assertEqual(h.seq.rules.ambientMax, 1, "override kept");
  assertEqual(window.MorkynSceneSequence.RULES.ambientMax, 3, "shared RULES untouched");
  let finishCalls = 0;
  const first = heldScene(h.seq, 1, "a", () => {
    finishCalls += 1;
  });
  const rec = recordingShow();
  h.seq.enqueueAmbient({ token: { turn: 1 }, text: "one", show: rec.show });
  h.seq.enqueueAmbient({ token: { turn: 1 }, text: "two", show: rec.show });
  assertEqual(h.named("ambient-dropped")[0].payload.text, "one", "ambientMax 1 drops the first");
  heldScene(h.seq, 2, "b");
  assertEqual(finishCalls, 1, "finishCurrentAt 1 finishes on the second scene");
  first.done();
  h.timers.advance(100);
  assertEqual(h.named("scene-timeout").length, 1, "short watchdog fires");
  assertEqual(rec.shown, ["two"], "the kept line shown after a");
});

test("default_export_is_a_sequencer_with_global_timers", () => {
  // The default object was created with window timers; window = {} has none,
  // so node's own timers are used. A scene that calls done() synchronously
  // never needs the watchdog, so this stays deterministic.
  const api = window.MorkynSceneSequence;
  assert(!api.isBusy(), "starts idle");
  const rec = recordingShow();
  api.enqueueAmbient({ token: { turn: 1 }, text: "idle line", show: rec.show });
  assertEqual(rec.shown, ["idle line"], "default sequencer shows idle ambient");
  api.enqueueScene({ token: { turn: 1 }, render: (done) => done() });
  assert(!api.isBusy(), "synchronous scene ends at once");
  assertEqual(api.lastShown().turn, 1, "lastShown");
  api.reset();
  assertEqual(api.lastShown(), null, "reset works on the default object");
});

/* ------------------------------------------------------------------------
   Runner
   ------------------------------------------------------------------------ */

function main() {
  try {
    global.window = {};
    require(MODULE);
  } catch (err) {
    console.error("HARNESS ERROR: module failed to load:", err && err.message);
    return 2;
  }
  if (!window.MorkynSceneSequence) {
    console.error("HARNESS ERROR: window.MorkynSceneSequence not set");
    return 2;
  }
  const failures = [];
  CASES.forEach(({ name, fn }) => {
    try {
      fn();
    } catch (err) {
      failures.push(`${name}: ${err && err.message}`);
    }
  });
  if (failures.length) {
    console.error("FAIL");
    failures.forEach((f) => console.error("  -", f));
    return 1;
  }
  console.log(`PASS  scene_sequence: ${CASES.length} cases`);
  return 0;
}

process.exit(main());
