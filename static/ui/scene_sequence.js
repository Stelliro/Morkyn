/* ==========================================================================
   Mørkyn UI · scene_sequence.js  (display sequencing)

   Status: built, not wired (TODO g17).

   A queue for the one narration area. Scenes (turn payloads) are shown one at a time; an ambient line that
   arrives while a scene is streaming is held and shown when that stream has finished; an ambient line whose
   turn is older than the last scene shown is dropped. A second scene waits for the first; when a third
   arrives the current one is finished at once instead of being cut (requestWait fight scenes). Pure
   sequencing: callers pass render(done) and show(text) callbacks, so this file never touches the DOM. Nothing
   is persisted and nothing in the live page loads or calls this file.

   Wiring (not done):
     static/app.js:displayTurnPayload() -> MorkynSceneSequence.enqueueScene({token: MorkynSceneSequence.tokenOf(payload),
         label: payload.input_kind || "turn", render: (done) => <today's body, calling done() in the stream's onDone
         or right after the synchronous innerHTML path>, finishNow: () => <finish the stream instantly>})
     static/app.js:showAmbientMoveLine() -> MorkynSceneSequence.enqueueAmbient({token: MorkynSceneSequence.tokenOf({state}),
         text, show: (t) => <today's body>})
     static/app.js:streamTextToTargets() -> expose a finishNow (clearInterval + full text + onDone) for the scene's handle
     static/app.js:applyTravelMoveFeedback() and requestWait() fight_scenes loop -> nothing more once the two above are wrapped
     static/app.js:rewindTurn() / startGame() -> MorkynSceneSequence.reset()
     static/index.html -> <script src="/static/ui/scene_sequence.js?v=__BUNDLE__"> after app.js

   Turn on:
     [ ] the script line in static/index.html (and static/popout.html if it shows narration)
     [ ] the two wraps in displayTurnPayload / showAmbientMoveLine
     [ ] reset() on rewind and new game
     [ ] no server change, no route, no prompt

   Tests: tools/test_scene_sequence.js (node)
   ========================================================================== */

(function () {
  "use strict";

  // The page's global object. In the browser this is window; the node test
  // sets global.window = {} before requiring the file, and nothing else is
  // read from it except the timers (which may be absent).
  const root = typeof window !== "undefined" ? window : globalThis;

  /* ------------------------------------------------------------------------
     Rules (data). The numbers are the design's; tests pin them.
     ------------------------------------------------------------------------ */

  const RULES = {
    ambientMax: 3, // held ambient lines; the oldest is dropped when a fourth arrives (reason "overflow")
    finishCurrentAt: 2, // when this many scenes are already waiting, the in-flight scene's finishNow() is called
    watchdogMs: 15000, // a scene that never calls done() is ended after this (reason "scene-timeout")
    staleRule: "turn_below_last_shown", // an ambient with token.turn < lastShown.turn is dropped on flush
    sameTurnAmbient: "show", // an ambient with token.turn == lastShown.turn is shown (a free step in the same turn)
    idleAmbient: "immediate", // nothing in flight and nothing queued -> show(text) synchronously
  };

  const EVENTS = [
    "scene-start",
    "scene-done",
    "scene-queued",
    "scene-timeout",
    "scene-finished-early",
    "ambient-shown",
    "ambient-held",
    "ambient-dropped",
    "reset",
  ];

  const DROP_REASONS = ["stale", "overflow", "reset"];

  /* ------------------------------------------------------------------------
     DisplayToken helpers (pure)
     ------------------------------------------------------------------------ */

  function intOrNull(value) {
    if (typeof value === "number") return Number.isFinite(value) ? Math.trunc(value) : null;
    if (typeof value === "string" && /^\s*-?\d+\s*$/.test(value)) return parseInt(value, 10);
    return null;
  }

  // "x,y" from a step target: the route sends [x, y] (main.py "step": {"to": [tx, ty]});
  // an {x, y} object is accepted too. Anything else is "".
  function stepOf(to) {
    if (Array.isArray(to) && to.length >= 2) {
      const x = intOrNull(to[0]);
      const y = intOrNull(to[1]);
      return x === null || y === null ? "" : `${x},${y}`;
    }
    if (to && typeof to === "object") {
      const x = intOrNull(to.x);
      const y = intOrNull(to.y);
      return x === null || y === null ? "" : `${x},${y}`;
    }
    return "";
  }

  // DisplayToken: {turn, step, seq}. turn is payload.turn when that is a number;
  // in a live turn payload payload.turn is the narration object and the number
  // is payload.state.turn, so an object turn falls through to its own .turn and
  // then to state.turn. seq is 0 here; the sequencer assigns it on enqueue.
  function tokenOf(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    let turn = intOrNull(p.turn);
    if (turn === null && p.turn && typeof p.turn === "object") turn = intOrNull(p.turn.turn);
    if (turn === null && p.state && typeof p.state === "object") turn = intOrNull(p.state.turn);
    const to = p.step && typeof p.step === "object" && p.step.to !== undefined
      ? p.step.to
      : p.travel && typeof p.travel === "object"
        ? p.travel.to
        : undefined;
    return { turn: turn === null ? 0 : turn, step: stepOf(to), seq: 0 };
  }

  function normalizeToken(token) {
    const t = token && typeof token === "object" ? token : {};
    return {
      turn: intOrNull(t.turn) ?? 0,
      step: typeof t.step === "string" ? t.step : "",
      seq: intOrNull(t.seq) ?? 0,
    };
  }

  // Order: turn, then seq.
  function compareTokens(a, b) {
    const ta = normalizeToken(a);
    const tb = normalizeToken(b);
    if (ta.turn !== tb.turn) return ta.turn < tb.turn ? -1 : 1;
    if (ta.seq !== tb.seq) return ta.seq < tb.seq ? -1 : 1;
    return 0;
  }

  function copyToken(token) {
    return token ? { turn: token.turn, step: token.step, seq: token.seq } : null;
  }

  /* ------------------------------------------------------------------------
     The sequencer
     ------------------------------------------------------------------------ */

  function create(options) {
    const opts = options && typeof options === "object" ? options : {};
    const rules = Object.assign({}, RULES, opts.rules && typeof opts.rules === "object" ? opts.rules : {});
    const timerHost = typeof opts.setTimeout === "function" ? null : root;
    const setTimer = typeof opts.setTimeout === "function" ? opts.setTimeout : root.setTimeout;
    const clearTimer = typeof opts.clearTimeout === "function" ? opts.clearTimeout : root.clearTimeout;
    const now = typeof opts.now === "function" ? opts.now : () => Date.now();
    const log =
      typeof opts.log === "function"
        ? opts.log
        : typeof console !== "undefined" && typeof console.warn === "function"
          ? (...args) => console.warn(...args)
          : () => {};

    const state = {
      inFlight: null,
      scenes: [],
      ambients: [],
      lastShown: null,
      seq: 0,
      nextId: 0,
      watchdog: null,
      listeners: {},
    };
    EVENTS.forEach((name) => {
      state.listeners[name] = [];
    });

    const nextId = () => {
      state.nextId += 1;
      return state.nextId;
    };
    const stamp = (token) => {
      state.seq += 1;
      const t = normalizeToken(token);
      t.seq = state.seq;
      return t;
    };
    const sceneInfo = (scene) => ({ id: scene.id, label: scene.label, token: copyToken(scene.token) });

    function emit(event, payload) {
      const fns = state.listeners[event] || [];
      fns.slice().forEach((fn) => {
        try {
          fn(payload);
        } catch (err) {
          log("scene_sequence listener failed", event, err);
        }
      });
    }

    function on(event, fn) {
      if (!EVENTS.includes(event)) throw new TypeError(`unknown scene_sequence event: ${event}`);
      if (typeof fn !== "function") throw new TypeError("on(event, fn): fn must be a function");
      state.listeners[event].push(fn);
      return () => {
        const list = state.listeners[event];
        const at = list.indexOf(fn);
        if (at >= 0) list.splice(at, 1);
      };
    }

    function armWatchdog(scene) {
      disarmWatchdog();
      if (typeof setTimer !== "function") return;
      const ms = Number(rules.watchdogMs);
      if (!(ms > 0)) return;
      state.watchdog = setTimer.call(timerHost, () => onWatchdog(scene), ms);
    }

    function disarmWatchdog() {
      if (state.watchdog === null) return;
      if (typeof clearTimer === "function") clearTimer.call(timerHost, state.watchdog);
      state.watchdog = null;
    }

    function onWatchdog(scene) {
      state.watchdog = null;
      if (state.inFlight !== scene || scene.ended) return;
      emit("scene-timeout", sceneInfo(scene));
      finishScene(scene, { timeout: true });
    }

    // Ends the in-flight scene, records it as the last shown, flushes held
    // ambients, then starts the next waiting scene. Every exit path of a
    // scene comes through here, so the queue cannot wedge.
    function finishScene(scene, meta) {
      if (scene.ended) return;
      scene.ended = true;
      disarmWatchdog();
      state.inFlight = null;
      state.lastShown = copyToken(scene.token);
      emit("scene-done", Object.assign(sceneInfo(scene), { error: !!(meta && meta.error), timeout: !!(meta && meta.timeout) }));
      flush();
      startNext();
    }

    function startNext() {
      if (state.inFlight !== null) return;
      const scene = state.scenes.shift();
      if (!scene) return;
      startScene(scene);
    }

    function startScene(scene) {
      state.inFlight = scene;
      emit("scene-start", sceneInfo(scene));
      armWatchdog(scene);
      const done = () => {
        if (state.inFlight !== scene || scene.ended) return; // done() twice, or for an old scene: ignored
        finishScene(scene, {});
      };
      scene.done = done;
      try {
        scene.render(done);
      } catch (err) {
        log("scene_sequence render failed", scene.label, err);
        if (state.inFlight === scene && !scene.ended) finishScene(scene, { error: true });
      }
    }

    function callFinishNow(scene, waiting) {
      if (!scene || scene.finishedEarly || typeof scene.finishNow !== "function") return false;
      scene.finishedEarly = true;
      emit("scene-finished-early", Object.assign(sceneInfo(scene), { waiting }));
      try {
        scene.finishNow();
      } catch (err) {
        log("scene_sequence finishNow failed", scene.label, err);
        if (state.inFlight === scene && !scene.ended) finishScene(scene, { error: true });
      }
      return true;
    }

    function makeScene(spec, render) {
      return {
        id: nextId(),
        token: stamp(spec.token),
        label: typeof spec.label === "string" && spec.label ? spec.label : "turn",
        render,
        finishNow: typeof spec.finishNow === "function" ? spec.finishNow : null,
        enqueuedAt: now(),
        ended: false,
        finishedEarly: false,
        done: null,
      };
    }

    function admitScene(scene) {
      if (state.inFlight === null && state.scenes.length === 0) {
        startScene(scene);
        return scene.id;
      }
      state.scenes.push(scene);
      emit("scene-queued", Object.assign(sceneInfo(scene), { waiting: state.scenes.length }));
      if (state.scenes.length >= Number(rules.finishCurrentAt)) callFinishNow(state.inFlight, state.scenes.length);
      return scene.id;
    }

    function enqueueScene(spec) {
      const s = spec && typeof spec === "object" ? spec : {};
      if (typeof s.render !== "function") throw new TypeError("enqueueScene: render(done) is required");
      return admitScene(makeScene(s, s.render));
    }

    // The imperative pair for a caller that renders itself: beginScene() gives
    // a handle, endScene(handle) ends it. The handle's render is a no-op.
    function beginScene(token, label, extra) {
      const e = extra && typeof extra === "object" ? extra : {};
      const scene = makeScene({ token, label, finishNow: e.finishNow }, () => {});
      admitScene(scene);
      return { id: scene.id, label: scene.label, token: copyToken(scene.token) };
    }

    function endScene(handle) {
      const scene = state.inFlight;
      if (!handle || !scene || scene.ended || handle.id !== scene.id) return false;
      finishScene(scene, {});
      return true;
    }

    function showAmbient(ambient) {
      try {
        ambient.show(ambient.text);
      } catch (err) {
        log("scene_sequence show failed", err);
      }
      emit("ambient-shown", { id: ambient.id, token: copyToken(ambient.token), text: ambient.text });
    }

    function dropAmbient(ambient, reason) {
      emit("ambient-dropped", { id: ambient.id, token: copyToken(ambient.token), text: ambient.text, reason });
    }

    function enqueueAmbient(spec) {
      const s = spec && typeof spec === "object" ? spec : {};
      if (typeof s.show !== "function") throw new TypeError("enqueueAmbient: show(text) is required");
      const text = String(s.text == null ? "" : s.text).trim();
      if (!text) return 0;
      const ambient = { id: nextId(), token: stamp(s.token), text, show: s.show, enqueuedAt: now() };
      if (!isBusy()) {
        showAmbient(ambient);
        return ambient.id;
      }
      state.ambients.push(ambient);
      const max = Number(rules.ambientMax);
      while (max >= 0 && state.ambients.length > max) dropAmbient(state.ambients.shift(), "overflow");
      if (state.ambients.includes(ambient)) {
        emit("ambient-held", { id: ambient.id, token: copyToken(ambient.token), text, held: state.ambients.length });
      }
      return ambient.id;
    }

    // Shows the held ambient lines in order, dropping the stale ones. While a
    // scene is in flight nothing is shown and {0, 0} comes back; the scene's
    // own end calls flush again.
    function flush() {
      const result = { shown: 0, dropped: 0 };
      if (state.inFlight !== null) return result;
      const held = state.ambients;
      state.ambients = [];
      held.forEach((ambient) => {
        if (state.lastShown && ambient.token.turn < state.lastShown.turn) {
          dropAmbient(ambient, "stale");
          result.dropped += 1;
        } else {
          showAmbient(ambient);
          result.shown += 1;
        }
      });
      return result;
    }

    function finishCurrent() {
      return callFinishNow(state.inFlight, state.scenes.length);
    }

    function isBusy() {
      return state.inFlight !== null || state.scenes.length > 0;
    }

    function pending() {
      return {
        inFlight: state.inFlight ? sceneInfo(state.inFlight) : null,
        scenes: state.scenes.length,
        ambients: state.ambients.length,
      };
    }

    function lastShown() {
      return copyToken(state.lastShown);
    }

    function reset() {
      disarmWatchdog();
      const held = state.ambients;
      const summary = { scenes: state.scenes.length + (state.inFlight ? 1 : 0), ambients: held.length };
      if (state.inFlight) state.inFlight.ended = true;
      state.inFlight = null;
      state.scenes = [];
      state.ambients = [];
      state.lastShown = null;
      held.forEach((ambient) => dropAmbient(ambient, "reset"));
      emit("reset", summary);
    }

    return {
      enqueueScene,
      beginScene,
      endScene,
      enqueueAmbient,
      flush,
      finishCurrent,
      isBusy,
      pending,
      lastShown,
      reset,
      on,
      rules: Object.freeze(Object.assign({}, rules)),
    };
  }

  /* ------------------------------------------------------------------------
     Export: the page-wide sequencer (window timers) plus the factory and the
     pure helpers on the same object.
     ------------------------------------------------------------------------ */

  const api = create();
  api.create = create;
  api.tokenOf = tokenOf;
  api.compareTokens = compareTokens;
  api.RULES = Object.freeze(Object.assign({}, RULES));
  api.EVENTS = Object.freeze(EVENTS.slice());
  api.DROP_REASONS = Object.freeze(DROP_REASONS.slice());

  root.MorkynSceneSequence = api;
})();
