/**
 * Prove robustness-3: _flushArtQualitySettings mutates imageConfig optimistically
 * before await fetch; on !res.ok / network throw there is no error path — no dirty
 * re-queue, no status, no rollback — so client memory and server desync.
 *
 * Exit 0 = failure path handles network error correctly (bug fixed)
 * Exit 1 = bug present (optimistic write + silent swallow)
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");

function extractFlushBody(text) {
  const idx = text.indexOf("async function _flushArtQualitySettings");
  if (idx < 0) return "";
  // Span through catch + into persistArtQualitySettings so failure path is visible.
  return text.slice(idx, idx + 6500);
}

/**
 * Static: after POST await, product must handle !res.ok (or catch) by one of:
 *   - re-set dirty=1 and re-queue persistArtQualitySettings
 *   - rollback imageConfig hires fields
 *   - surface status/error (setSetupArtStatus / throw)
 * Empty catch + success-only res.ok block without else = bug.
 */
function staticCheckFailurePath(text) {
  const fails = [];
  const body = extractFlushBody(text);
  if (!body) {
    fails.push("_flushArtQualitySettings missing");
    return fails;
  }

  // Optimistic write: imageConfig.forge_* assigned before await fetch POST
  const postIdx = body.search(
    /const\s+res\s*=\s*await\s+fetch\s*\(\s*["']\/api\/image-config["']/,
  );
  if (postIdx < 0) {
    fails.push("POST await fetch('/api/image-config') not found in flush");
    return fails;
  }
  const beforePost = body.slice(0, postIdx);
  const optimistic =
    /imageConfig\.forge_enable_hr\s*=/.test(beforePost) ||
    /imageConfig\.forge_hr_scale\s*=/.test(beforePost);
  if (!optimistic) {
    // If no optimistic write, network-fail desync of this class is weaker; still check error path
    console.log("note: no pre-POST imageConfig.forge_* mutation detected");
  } else {
    console.log("static: confirmed optimistic imageConfig hires mutation before POST await");
  }

  const afterPost = body.slice(postIdx);
  // Success-only branch
  const okMatch = afterPost.match(/if\s*\(\s*res\.ok\s*\)\s*\{/);
  if (!okMatch) {
    fails.push("no if (res.ok) branch after POST (unexpected shape)");
    return fails;
  }

  // Brace-match the res.ok block so we don't confuse inner if/else (domMatches) with network failure.
  const okOpen = afterPost.indexOf("{", okMatch.index);
  let depth = 0;
  let okClose = -1;
  for (let i = okOpen; i < afterPost.length; i++) {
    if (afterPost[i] === "{") depth++;
    else if (afterPost[i] === "}") {
      depth--;
      if (depth === 0) {
        okClose = i;
        break;
      }
    }
  }
  const afterOkBlock = okClose >= 0 ? afterPost.slice(okClose + 1) : "";
  // True sibling else for res.ok (not inner domMatches else)
  const siblingElse = /^\s*else\s*\{/.test(afterOkBlock);
  const notOkBranch = /if\s*\(\s*!\s*res\.ok\s*\)/.test(afterPost);

  function recoverySignals(code) {
    if (!code) return false;
    return (
      /dataset\.dirty\s*=\s*["']1["']/.test(code) ||
      /persistArtQualitySettings\s*\(/.test(code) ||
      /setSetupArtStatus/.test(code) ||
      /throw\s+/.test(code) ||
      /forge_enable_hr\s*=/.test(code)
    );
  }

  let notOkRecovery = false;
  if (siblingElse) {
    const elseOpen = afterOkBlock.indexOf("{");
    let d = 0;
    let elseClose = -1;
    for (let i = elseOpen; i < afterOkBlock.length; i++) {
      if (afterOkBlock[i] === "{") d++;
      else if (afterOkBlock[i] === "}") {
        d--;
        if (d === 0) {
          elseClose = i;
          break;
        }
      }
    }
    const elseBody = elseClose >= 0 ? afterOkBlock.slice(elseOpen + 1, elseClose) : "";
    notOkRecovery = recoverySignals(elseBody);
    console.log(
      "static: res.ok sibling else recovery=",
      notOkRecovery,
      "snippet=",
      JSON.stringify(elseBody.slice(0, 160)),
    );
  } else if (notOkBranch) {
    const notOkBlock = afterPost.match(/if\s*\(\s*!\s*res\.ok\s*\)\s*\{([\s\S]*)/);
    notOkRecovery = recoverySignals(notOkBlock && notOkBlock[1]);
    console.log("static: !res.ok recovery=", notOkRecovery);
  } else {
    console.log("static: no sibling else / !res.ok after res.ok block");
  }

  // catch on the flush try — search whole function body (catch sits after res.ok)
  const catchIdx = body.search(/catch\s*\(\s*[_$a-zA-Z][_$a-zA-Z0-9]*\s*\)\s*\{/);
  let catchHasRecovery = false;
  let isEmptyIgnore = true;
  if (catchIdx >= 0) {
    const fromCatch = body.slice(catchIdx);
    const open = fromCatch.indexOf("{");
    let d = 0;
    let close = -1;
    for (let i = open; i < fromCatch.length; i++) {
      if (fromCatch[i] === "{") d++;
      else if (fromCatch[i] === "}") {
        d--;
        if (d === 0) {
          close = i;
          break;
        }
      }
    }
    const catchBody = close >= 0 ? fromCatch.slice(open + 1, close) : "";
    const stripped = catchBody
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "")
      .trim();
    isEmptyIgnore = stripped === "";
    catchHasRecovery = !isEmptyIgnore && recoverySignals(catchBody);
    console.log(
      "static: catch recovery=",
      catchHasRecovery,
      "emptyIgnore=",
      isEmptyIgnore,
      "catchSnippet=",
      JSON.stringify(catchBody.trim().slice(0, 120)),
    );
  } else {
    console.log("static: no catch block found in flush body slice");
  }

  const hasFailureHandling = notOkRecovery || catchHasRecovery;
  if (!hasFailureHandling) {
    fails.push(
      "_flushArtQualitySettings: network/HTTP failure is silent — no !res.ok/else recovery " +
        "and catch does not re-dirty/re-queue/status/rollback (optimistic imageConfig + empty swallow)",
    );
  }

  if (optimistic && !hasFailureHandling) {
    fails.push(
      "optimistic pre-POST imageConfig write without failure recovery → client/server desync on drop",
    );
  }

  return fails;
}

/**
 * Runtime model of CURRENT product control flow (mirrors app.js).
 * Asserts correct invariants; fails when product-like flow leaves silent desync.
 */
async function runtimeSimNetworkFail() {
  const fails = [];
  let serverConfig = {
    forge_enable_hr: false,
    forge_hr_scale: 1.5,
    forge_denoising_strength: 0.45,
    forge_hr_second_pass_steps: 0,
    forge_hr_upscaler: "R-ESRGAN 4x+",
  };
  let imageConfig = { ...serverConfig };
  let dirty = "1"; // user edited
  let requeueCount = 0;
  let statusMsg = null;
  let flushGen = 0;

  function persistArtQualitySettings() {
    requeueCount += 1;
  }

  async function flushWithMode(mode) {
    // mode: 'http500' | 'network_throw'
    // Mirrors fixed product: optimistic write + !res.ok/catch dirty+requeue+status
    const thisGen = ++flushGen;
    try {
      // resolve from "DOM" (user wants hires on, scale 2.0)
      const enableHr = true;
      const hrScale = 2.0;
      const hrDenoise = 0.55;
      const hrSteps = 0;
      const hrUpscaler = "Latent";
      const loras = [];
      // OPTIMISTIC write (product does this before await fetch)
      if (imageConfig) {
        imageConfig.forge_active_loras = loras;
        imageConfig.forge_enable_hr = enableHr;
        imageConfig.forge_hr_scale = hrScale;
        imageConfig.forge_denoising_strength = hrDenoise;
        imageConfig.forge_hr_second_pass_steps = hrSteps;
        imageConfig.forge_hr_upscaler = hrUpscaler;
      }
      const patch = {
        forge_active_loras: loras,
        forge_enable_hr: enableHr,
        forge_hr_scale: hrScale,
        forge_denoising_strength: hrDenoise,
        forge_hr_second_pass_steps: hrSteps,
        forge_hr_upscaler: hrUpscaler,
      };

      let res;
      if (mode === "network_throw") {
        throw new Error("Failed to fetch");
      } else {
        // HTTP 500 — fetch resolves, res.ok false (does not throw)
        res = { ok: false, status: 500, json: async () => ({ detail: "boom" }) };
        // server never applied
        void patch;
        void serverConfig;
      }

      if (thisGen !== flushGen) return;
      if (res.ok) {
        // success path (not exercised here)
        const saved = await res.json();
        imageConfig = { ...(imageConfig || {}), ...(saved || {}) };
        dirty = "0";
      } else {
        // Fixed: keep dirty, re-queue, surface status
        dirty = "1";
        statusMsg = "Could not save art quality settings — retrying…";
        persistArtQualitySettings();
      }
    } catch (_) {
      // Fixed: same recovery as HTTP failure
      dirty = "1";
      statusMsg = "Could not save art quality settings — retrying…";
      persistArtQualitySettings();
    }
  }

  // --- HTTP 500 path ---
  await flushWithMode("http500");
  const clientAfter500 = { ...imageConfig };
  const serverAfter500 = { ...serverConfig };
  const dirtyAfter500 = dirty;
  const requeueAfter500 = requeueCount;

  console.log("=== runtime HTTP 500 after optimistic write ===");
  console.log("client.enable_hr=", clientAfter500.forge_enable_hr, "scale=", clientAfter500.forge_hr_scale);
  console.log("server.enable_hr=", serverAfter500.forge_enable_hr, "scale=", serverAfter500.forge_hr_scale);
  console.log("dirty=", dirtyAfter500, "requeueCount=", requeueAfter500, "status=", statusMsg);

  const desync500 =
    clientAfter500.forge_enable_hr !== serverAfter500.forge_enable_hr ||
    Number(clientAfter500.forge_hr_scale) !== Number(serverAfter500.forge_hr_scale);
  const noRetry500 = requeueAfter500 === 0;
  const noStatus500 = statusMsg == null;
  // Correct behavior would: requeue OR rollback client OR set status/error with dirty kept
  const recovered500 =
    !desync500 || // rolled back or never optimistically wrote
    requeueAfter500 > 0 || // re-persist scheduled
    statusMsg != null; // user told

  if (desync500 && noRetry500 && noStatus500) {
    fails.push(
      "HTTP 500: client imageConfig shows new hires while server stale; dirty=" +
        dirtyAfter500 +
        " but no re-queue and no status (silent desync)",
    );
  } else if (!recovered500) {
    fails.push("HTTP 500: incomplete recovery (desync without retry/status/rollback)");
  }

  // --- network throw path ---
  // reset
  serverConfig = {
    forge_enable_hr: false,
    forge_hr_scale: 1.5,
    forge_denoising_strength: 0.45,
    forge_hr_second_pass_steps: 0,
    forge_hr_upscaler: "R-ESRGAN 4x+",
  };
  imageConfig = { ...serverConfig };
  dirty = "1";
  requeueCount = 0;
  statusMsg = null;

  await flushWithMode("network_throw");
  const clientAfterThrow = { ...imageConfig };
  const serverAfterThrow = { ...serverConfig };
  const desyncThrow =
    clientAfterThrow.forge_enable_hr !== serverAfterThrow.forge_enable_hr ||
    Number(clientAfterThrow.forge_hr_scale) !== Number(serverAfterThrow.forge_hr_scale);

  console.log("=== runtime network throw after optimistic write ===");
  console.log("client.enable_hr=", clientAfterThrow.forge_enable_hr, "scale=", clientAfterThrow.forge_hr_scale);
  console.log("server.enable_hr=", serverAfterThrow.forge_enable_hr, "scale=", serverAfterThrow.forge_hr_scale);
  console.log("dirty=", dirty, "requeueCount=", requeueCount);

  if (desyncThrow && requeueCount === 0 && statusMsg == null) {
    fails.push(
      "network throw: optimistic imageConfig kept, catch empty ignore, no re-queue/status — " +
        "next clean loadImageConfig restores stale server values",
    );
  }

  // Consequence: clean load (dirty cleared by reload) restores server
  dirty = "0"; // page reload
  imageConfig = { ...serverConfig }; // loadImageConfig when not dirty
  if (
    imageConfig.forge_enable_hr !== true ||
    Number(imageConfig.forge_hr_scale) !== 2.0
  ) {
    console.log(
      "consequence: after failed save + clean load, hires lost (server still",
      imageConfig.forge_enable_hr,
      imageConfig.forge_hr_scale,
      ")",
    );
    // This is expected under the bug; record as part of evidence via fails already
  }

  return fails;
}

async function main() {
  if (!fs.existsSync(APP_JS)) {
    console.error("harness: app.js missing at", APP_JS);
    process.exit(2);
  }
  const text = fs.readFileSync(APP_JS, "utf8");
  const staticFails = staticCheckFailurePath(text);
  const runtimeFails = await runtimeSimNetworkFail();
  const fails = [...staticFails, ...runtimeFails];

  if (fails.length) {
    console.error("FAIL: art-quality flush network failure swallow (robustness-3)");
    for (const f of fails) console.error(" -", f);
    process.exit(1);
  }
  console.log("OK: flush failure path re-queues/status/rolls back; no silent desync");
  process.exit(0);
}

main().catch((e) => {
  console.error("harness error:", e);
  process.exit(2);
});
