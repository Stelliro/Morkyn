/**
 * Prove: debounced persistArtQualitySettings pending Promise never settles
 * after clearTimeout, so await prior hangs forever.
 *
 * Mirrors static/app.js persistArtQualitySettings debounce + flush control flow
 * (as of robustness-1 candidate):
 *   - Debounce creates Promise that only resolve()s inside setTimeout callback
 *   - flush:true (and re-debounce) clearTimeout without resolve/reject of prior
 *   - flush then awaits that prior → permanent hang
 *
 * Exit 0 = hang not observed (disproven / fixed)
 * Exit 1 = hang proven (flush body never runs / await times out)
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

const DEBOUNCE_MS = 280;
const HANG_TIMEOUT_MS = 600;

// --- Mirror product control flow (fixed: settle debounce Promise on clearTimeout) ---
let _persistArtQualityTimer = null;
let _persistArtQualityPending = null;
let _persistArtQualitySettle = null;
let flushBodyRuns = 0;

async function _flushArtQualitySettings() {
  flushBodyRuns += 1;
}

/** Cancel debounce timer and settle its Promise so await-prior never hangs. */
function _settleArtQualityDebounce() {
  if (_persistArtQualityTimer != null) {
    clearTimeout(_persistArtQualityTimer);
    _persistArtQualityTimer = null;
  }
  if (typeof _persistArtQualitySettle === "function") {
    const resolve = _persistArtQualitySettle;
    _persistArtQualitySettle = null;
    try {
      resolve();
    } catch (_) {
      /* ignore */
    }
  }
}

/**
 * Product-shaped debounce/flush (see static/app.js persistArtQualitySettings).
 * Fixed shape: settle outstanding debounce Promise before clearTimeout/re-debounce.
 */
function persistArtQualitySettings({ flush = false } = {}) {
  if (flush) {
    _settleArtQualityDebounce();
    const prior = _persistArtQualityPending;
    _persistArtQualityPending = (async () => {
      if (prior) {
        try {
          await prior;
        } catch (_) {
          /* ignore */
        }
      }
      await _flushArtQualitySettings();
    })();
    return _persistArtQualityPending;
  }
  _settleArtQualityDebounce();
  const prior = _persistArtQualityPending;
  _persistArtQualityPending = new Promise((resolve) => {
    _persistArtQualitySettle = resolve;
    _persistArtQualityTimer = setTimeout(async () => {
      _persistArtQualityTimer = null;
      _persistArtQualitySettle = null;
      if (prior) {
        try {
          await prior;
        } catch (_) {
          /* ignore */
        }
      }
      await _flushArtQualitySettings();
      resolve();
    }, DEBOUNCE_MS);
  });
  return _persistArtQualityPending;
}

function withTimeout(promise, ms, label) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      reject(new Error(`TIMEOUT after ${ms}ms: ${label}`));
    }, ms);
    promise.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}

/**
 * Static: product source has debounce Promise that only resolve()s in timer,
 * and flush clearTimeouts without settling prior debounce pending.
 */
function assertProductSourceHasHangShape() {
  const text = fs.readFileSync(APP_JS, "utf8");
  const idx = text.indexOf("function persistArtQualitySettings");
  if (idx < 0) throw new Error("persistArtQualitySettings missing in app.js");
  // Enough of the function body (debounce + flush)
  const body = text.slice(idx, idx + 2000);

  const hasFlushClear =
    /if\s*\(\s*flush\s*\)[\s\S]*?clearTimeout\s*\(\s*_persistArtQualityTimer\s*\)/.test(body);
  const hasDebouncePromise =
    /_persistArtQualityPending\s*=\s*new Promise\s*\(\s*\(\s*resolve\s*\)\s*=>/.test(body);
  const resolveOnlyInTimeout =
    /setTimeout\s*\(\s*async\s*\(\s*\)\s*=>[\s\S]*?resolve\s*\(\s*\)/.test(body);
  // flush awaits prior (the hang surface)
  const flushAwaitsPrior =
    /if\s*\(\s*flush\s*\)[\s\S]*?await\s+prior/.test(body) ||
    /const prior = _persistArtQualityPending[\s\S]*?await prior/.test(body);

  // Does flush settle prior timer promise on clearTimeout? Look for resolve/reject of
  // a stored settle fn before/after clearTimeout in flush branch — product currently does not.
  const flushBranch = body.match(/if\s*\(\s*flush\s*\)\s*\{[\s\S]*?\n  \}/);
  const flushText = flushBranch ? flushBranch[0] : body.slice(0, 800);
  const settlesOnClear =
    /_persistArtQualitySettle|reject\s*\(\s*prior|resolve\s*\(\s*\).*clearTimeout|clearTimeout[\s\S]{0,120}resolve/.test(
      flushText,
    );

  return {
    hasFlushClear,
    hasDebouncePromise,
    resolveOnlyInTimeout,
    flushAwaitsPrior,
    settlesOnClear,
    hangShape:
      hasFlushClear &&
      hasDebouncePromise &&
      resolveOnlyInTimeout &&
      flushAwaitsPrior &&
      !settlesOnClear,
  };
}

async function scenarioDebounceThenFlush() {
  flushBodyRuns = 0;
  _persistArtQualityTimer = null;
  _persistArtQualityPending = null;

  // User edits scale → debounce starts
  const debounced = persistArtQualitySettings({ flush: false });
  if (!_persistArtQualityTimer) {
    throw new Error("harness: debounce did not arm timer");
  }

  // Within window: Generate → flush:true (clears timer, awaits prior)
  await new Promise((r) => setTimeout(r, 40));
  const flushP = persistArtQualitySettings({ flush: true });

  try {
    await withTimeout(flushP, HANG_TIMEOUT_MS, "flush after debounce");
    return { hung: false, flushBodyRuns };
  } catch (e) {
    if (String(e.message || e).startsWith("TIMEOUT")) {
      return {
        hung: true,
        flushBodyRuns,
        error: String(e.message || e),
        // prior still pending?
        priorPending: debounced,
      };
    }
    throw e;
  }
}

async function scenarioRedeBounce() {
  flushBodyRuns = 0;
  _persistArtQualityTimer = null;
  _persistArtQualityPending = null;

  const p1 = persistArtQualitySettings({ flush: false });
  await new Promise((r) => setTimeout(r, 40));
  // Second keystroke: clearTimeout first timer without resolving p1
  const p2 = persistArtQualitySettings({ flush: false });

  // Wait past debounce so p2's timer should fire and await p1
  try {
    await withTimeout(p2, DEBOUNCE_MS + HANG_TIMEOUT_MS, "second debounce after clearTimeout");
    return { hung: false, flushBodyRuns };
  } catch (e) {
    if (String(e.message || e).startsWith("TIMEOUT")) {
      return { hung: true, flushBodyRuns, error: String(e.message || e) };
    }
    throw e;
  }
}

async function main() {
  let staticInfo;
  try {
    staticInfo = assertProductSourceHasHangShape();
  } catch (e) {
    console.error("harness/static error:", e.message || e);
    process.exit(2);
  }

  console.log("=== debounce → flush hang harness ===");
  console.log("static hang-shape:", JSON.stringify(staticInfo));

  const s1 = await scenarioDebounceThenFlush();
  console.log("scenario debounce→flush:true:", JSON.stringify({
    hung: s1.hung,
    flushBodyRuns: s1.flushBodyRuns,
    error: s1.error || null,
  }));

  const s2 = await scenarioRedeBounce();
  console.log("scenario re-debounce:", JSON.stringify({
    hung: s2.hung,
    flushBodyRuns: s2.flushBodyRuns,
    error: s2.error || null,
  }));

  const proven =
    staticInfo.hangShape && (s1.hung || s2.hung) && flushBodyRuns === 0
      ? true
      : s1.hung || s2.hung;

  // Stricter: hang if either scenario hung and flush body never completed under timeout
  if (s1.hung || s2.hung) {
    console.error(
      "FAIL (bug proven): clearTimeout of debounce timer does not settle prior Promise; " +
        "await prior hangs; _flushArtQualitySettings runs=" +
        (s1.flushBodyRuns + s2.flushBodyRuns),
    );
    process.exit(1);
  }

  if (staticInfo.hangShape) {
    console.error(
      "WARN: product still has hang-prone shape but sim did not hang — unexpected",
    );
    process.exit(2);
  }

  console.log("OK: debounce pending settles / flush does not hang");
  process.exit(0);
}

main().catch((e) => {
  console.error("harness error:", e);
  process.exit(2);
});
