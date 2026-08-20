/**
 * Regression: concurrent _flushArtQualitySettings POSTs must be serialized /
 * stale completions must not overwrite newer user intent.
 *
 * Mirrors static/app.js persistArtQualitySettings / _flushArtQualitySettings
 * after the robustness-1 fix:
 *   - flush awaits prior _persistArtQualityPending before starting a new flush
 *   - flush generation token ignores late merges from older gens
 *   - success path only force-merges when this flush is still latest
 *
 * Scenario:
 *   (1) Hires ON → flush A captures enableHr=true, POST hangs
 *   (2) Hires OFF → flush B (flush:true) awaits A, then captures enableHr=false
 *   (3) A completes, then B's POST completes
 * Expect (fixed): final imageConfig.forge_enable_hr === false (last user intent)
 *
 * Exit 0 = race fixed (final state matches last intent + static serialize guard)
 * Exit 1 = race still present or static guard missing
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

// --- Controllable mock server state ---
let serverConfig = { forge_enable_hr: false };
/** @type {Map<number, {patch: object, resolve: (v:any)=>void}>} */
const pendingPosts = new Map();
let postSeq = 0;
/** ordered log of completed posts (server-applied) */
const appliedOrder = [];

function mockFetch(url, opts = {}) {
  const u = String(url);
  if (!u.includes("/api/image-config")) {
    return Promise.reject(new Error("unexpected url " + u));
  }
  if (!opts.method || opts.method.toUpperCase() === "GET") {
    return Promise.resolve({
      ok: true,
      json: async () => ({ ...serverConfig }),
    });
  }
  if (opts.method.toUpperCase() === "POST") {
    const patch = JSON.parse(opts.body);
    const id = ++postSeq;
    return new Promise((resolve) => {
      pendingPosts.set(id, {
        patch,
        resolve: (body) => {
          // Server applies whatever arrives (last-write-wins at network layer)
          serverConfig = { ...serverConfig, ...patch };
          appliedOrder.push({ id, forge_enable_hr: patch.forge_enable_hr });
          resolve({
            ok: true,
            json: async () => ({ ...serverConfig }),
          });
        },
      });
    });
  }
  return Promise.reject(new Error("bad method"));
}

// --- Mirror of fixed app.js flush/persist (no DOM) ---
let imageConfig = { forge_enable_hr: false };
let currentEnableHr = false; // stand-in for resolveArtHiresSettings() from UI
let _persistArtQualityTimer = null;
let _persistArtQualityPending = null;
let _artQualityFlushGen = 0;

async function _flushArtQualitySettings({ silent = true } = {}) {
  const flushGen = ++_artQualityFlushGen;
  // Capture at start — only after prior work has settled (serialize in persist)
  const enableHr = currentEnableHr;
  if (imageConfig) {
    imageConfig.forge_enable_hr = enableHr;
  }
  const patch = { forge_enable_hr: enableHr };
  const res = await mockFetch("/api/image-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (flushGen !== _artQualityFlushGen) return; // stale gen — ignore merge
  if (res.ok) {
    const saved = await res.json();
    if (flushGen !== _artQualityFlushGen) return;
    // Merge only when this flush is still the latest generation
    imageConfig = {
      ...(imageConfig || {}),
      ...(saved || {}),
      forge_enable_hr: enableHr,
    };
  }
}

function persistArtQualitySettings({ silent = true, flush = false } = {}) {
  // Fixed control flow: await prior pending before new flush
  if (flush) {
    clearTimeout(_persistArtQualityTimer);
    _persistArtQualityTimer = null;
    const prior = _persistArtQualityPending;
    _persistArtQualityPending = (async () => {
      if (prior) {
        try {
          await prior;
        } catch (_) {
          /* ignore */
        }
      }
      await _flushArtQualitySettings({ silent });
    })();
    return _persistArtQualityPending;
  }
  clearTimeout(_persistArtQualityTimer);
  const prior = _persistArtQualityPending;
  _persistArtQualityPending = new Promise((resolve) => {
    _persistArtQualityTimer = setTimeout(async () => {
      if (prior) {
        try {
          await prior;
        } catch (_) {
          /* ignore */
        }
      }
      await _flushArtQualitySettings({ silent });
      resolve();
    }, 280);
  });
  return _persistArtQualityPending;
}

function resolvePost(id) {
  const p = pendingPosts.get(id);
  if (!p) throw new Error("no pending post " + id);
  pendingPosts.delete(id);
  p.resolve();
}

function assertStaticSourceSerialized() {
  const text = fs.readFileSync(APP_JS, "utf8");
  const idx = text.indexOf("function persistArtQualitySettings");
  if (idx < 0) throw new Error("persistArtQualitySettings missing in app.js");
  const body = text.slice(idx, idx + 1200);
  if (!/if\s*\(\s*flush\s*\)/.test(body)) {
    throw new Error("flush branch missing");
  }
  if (!/clearTimeout\s*\(\s*_persistArtQualityTimer\s*\)/.test(body)) {
    throw new Error("flush does not clearTimeout timer");
  }
  const flushRegion = text.slice(
    text.indexOf("async function _flushArtQualitySettings"),
    text.indexOf("async function _flushArtQualitySettings") + 3500,
  );
  const awaitsPrior =
    /await\s+_persistArtQualityPending/.test(body) ||
    /await\s+prior/.test(body) ||
    /_persistArtQualityInFlight/.test(text.slice(idx - 200, idx + 1400));
  const hasToken =
    /_artQualityFlushGen|flushGen|flush(Id|Token|Gen|Generation)/.test(flushRegion) ||
    /_artQualityFlushGen/.test(text);
  const hasAbort = /AbortController/.test(flushRegion);
  const serialized = awaitsPrior || hasToken || hasAbort;
  return { awaitsPrior, hasToken, hasAbort, serialized, bodySnippet: body.slice(0, 500) };
}

async function runRace() {
  const staticInfo = assertStaticSourceSerialized();

  // (1) User turns Hires ON, immediate flush A
  currentEnableHr = true;
  const pA = persistArtQualitySettings({ flush: true });
  await Promise.resolve();
  await Promise.resolve();
  if (pendingPosts.size !== 1) {
    console.error("FAIL harness: expected 1 pending POST after A, got", pendingPosts.size);
    process.exit(2);
  }
  const idA = 1;

  // (2) User turns Hires OFF, flush:true — must await A (serialize), not open concurrent POST
  currentEnableHr = false;
  const pB = persistArtQualitySettings({ flush: true });
  await Promise.resolve();
  await Promise.resolve();
  // With serialize: only A's POST in flight until A completes
  if (pendingPosts.size > 1) {
    console.error(
      "FAIL: concurrent POSTs still allowed after fix (pending=",
      pendingPosts.size,
      ") — expected serialize to 1 in-flight",
    );
    process.exit(1);
  }

  // (3) A completes (captured ON at start). B then captures OFF and POSTs.
  resolvePost(idA);
  // Let A settle and B start its flush
  await Promise.resolve();
  await Promise.resolve();
  // Wait until B registered its POST (or finished if mock is sync — not)
  let spins = 0;
  while (pendingPosts.size < 1 && spins < 20) {
    await Promise.resolve();
    spins++;
  }
  if (pendingPosts.size !== 1) {
    // B may already have completed if something resolved early — check final state below
  } else {
    const idB = [...pendingPosts.keys()][0];
    resolvePost(idB);
  }
  await pA;
  await pB;

  const after_client = imageConfig.forge_enable_hr;
  const after_server = serverConfig.forge_enable_hr;
  const lastUserIntent = false; // OFF

  console.log("=== hires flush race harness (fixed semantics) ===");
  console.log("appliedOrder:", JSON.stringify(appliedOrder));
  console.log("final: client=", after_client, "server=", after_server);
  console.log("last user intent OFF");
  console.log("static serialize (await prior / token / Abort):", staticInfo.serialized, {
    awaitsPrior: staticInfo.awaitsPrior,
    hasToken: staticInfo.hasToken,
    hasAbort: staticInfo.hasAbort,
  });

  if (!staticInfo.serialized) {
    console.error("FAIL: product source lacks await-prior / flush token / AbortController guard");
    process.exit(1);
  }

  if (after_client !== lastUserIntent || after_server !== lastUserIntent) {
    console.error(
      "FAIL: final state does not match last intent OFF; client=",
      after_client,
      "server=",
      after_server,
    );
    process.exit(1);
  }

  // Last applied POST should be OFF (B). A may have applied ON first.
  const lastApplied = appliedOrder[appliedOrder.length - 1];
  if (!lastApplied || lastApplied.forge_enable_hr !== false) {
    console.error("FAIL: last server apply was not OFF", lastApplied);
    process.exit(1);
  }

  console.log("OK: flushes serialized; final enable_hr matches last intent OFF");
  process.exit(0);
}

runRace().catch((e) => {
  console.error("harness error:", e);
  process.exit(2);
});
