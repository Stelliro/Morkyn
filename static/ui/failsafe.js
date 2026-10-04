/* ==========================================================================
   Mørkyn UI · failsafe.js  (behaviour layer)

   When the model fails, stop, explain, and offer a way on.

   The server classifies a failure into a "problem": a code, a title, a
   summary, tips the player can act on, and sometimes a fallback they may
   accept. This script shows it:

     ask(problem)     a dialog with the tips and the choices. Resolves to
                      "fallback" (continue anyway), "retry", "settings", or
                      "dismiss". A fallback of kind "endpoint" is applied here
                      (one POST) and then resolves "retry"; a fallback of kind
                      "turn_fallback" resolves "fallback" so the caller resends
                      the turn with allow_fallback set.
     notice(problem)  the same dialog without a fallback, for background
                      status errors; the same problem is not shown twice in a
                      minute.
     parseError(raw)  reads the problem out of an HTTP error body, or builds
                      one from plain text with the client-side rules below.
     tipsHtml(p)      a small tips list for inline status areas.

   Classic script loaded after app.js. Layout in styles.css ("failsafe"
   block), look in ui/skin.css section 12. Rulebook: docs/UI_RULEBOOK.md §3.7
   ========================================================================== */

(function () {
  "use strict";

  const esc = (value) =>
    typeof window.escapeHtml === "function"
      ? window.escapeHtml(value)
      : String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  // Mirror of app/failsafe.py for errors that arrive as plain text. Keep the
  // two in step; the server copy is the authority.
  const RULES = [
    ["out_of_memory", ["out of memory", "failed to allocate", "cudamalloc", "bad_alloc", "memoryerror", "not enough memory", "insufficient memory", "unable to allocate", "cuda error", "kv cache", "kv_cache", "did not load)", "n_ctx"]],
    ["engine_missing", ["could not import llama_cpp", "no module named"]],
    ["model_missing", ["no model loaded", "set mle_model", "no such file", "does not exist", "missing model", "model file", "not found"]],
    ["server_unreachable", ["connection refused", "econnrefused", "winerror 10061", "failed to establish", "max retries", "name or service not known", "getaddrinfo", "connect call failed", "remote end closed", "connection reset", "unreachable", "could not start managed", "failed to fetch", "networkerror", "load failed", "server did not", "not answering"]],
    ["auth", ["unauthorized", "invalid api key", "incorrect api key", "forbidden", "authentication"]],
    ["rate_limit", ["rate limit", "too many requests", "quota exceeded", "429"]],
    ["timeout", ["timed out", "timeout", "deadline exceeded"]],
    ["bad_output", ["json", "malformed", "non-object", "could not parse", "readable narration", "echoed the setup schema", "no usable", "empty completion", "empty response", "did not include narration"]],
  ];

  const COPY = {
    out_of_memory: {
      title: "The model did not fit in memory",
      summary: "Loading or running the model ran out of RAM or video memory.",
      tips: [
        "Close apps using a lot of RAM or video memory: browsers with many tabs, games, image tools, other model servers.",
        "Lower Context tokens in the Gatehouse menu (or AI_RPG_CONTEXT_TOKENS). 8192 is enough for most scenes.",
        "Pick a smaller quantization of the same model, for example Q4 instead of Q8, or a smaller model.",
        "If the model runs on the GPU, set fewer GPU layers so part of it stays in system RAM.",
      ],
    },
    engine_missing: {
      title: "The local engine is not installed",
      summary: "Python could not import llama_cpp, so no GGUF can run in-process.",
      tips: ["Run the launcher once with the install step, or run: pip install llama-cpp-python inside .venv.", "Or switch Provider in LLM settings to a llama.cpp server or a cloud API."],
    },
    model_missing: {
      title: "No model file at that path",
      summary: "The engine is set to a GGUF it cannot find.",
      tips: ["Open LLM settings and point Model Path at an existing .gguf file.", "Or drop the file into data/mle-models/ and set MLE model to its name.", "Check the spelling and the drive letter; a moved download is the usual cause."],
    },
    server_unreachable: {
      title: "The LLM server is not answering",
      summary: "Nothing is listening at the configured address, or a firewall is in the way.",
      tips: [
        "Start the llama.cpp server (or the API gateway) and press Test Connection in LLM settings.",
        "Check the Server URL and port; the default local server is http://localhost:8080.",
        "If it started a moment ago, give it time to load the model, then retry.",
      ],
    },
    auth: {
      title: "The API rejected the key",
      summary: "The cloud provider answered that the key is missing, wrong, or not allowed for this model.",
      tips: ["Paste the key again in LLM settings; keys are easy to truncate when copied.", "Make sure the key belongs to the provider selected under API preset.", "Check the account has access to the chosen model and has credit."],
    },
    rate_limit: {
      title: "The API is rate-limiting requests",
      summary: "Too many requests, or the account's quota is used up.",
      tips: ["Wait a minute and retry.", "Lower the Soft and Hard token caps so each turn asks for less.", "Check the provider dashboard for quota or billing limits."],
    },
    timeout: {
      title: "The model took too long",
      summary: "No answer arrived before the time limit.",
      tips: ["Lower the Soft and Hard token caps in LLM settings so turns are shorter.", "Close other heavy apps; a model sharing the GPU or CPU slows down a lot.", "A smaller model or a smaller quantization answers faster on this hardware."],
    },
    bad_output: {
      title: "The model answered, but not in a usable shape",
      summary: "The reply could not be read as a scene.",
      tips: ["Retry once; small models occasionally drop the format.", "Raise the Hard token cap a little so the reply is not cut off mid-sentence.", "If it keeps happening with one model, try a different quantization or model."],
    },
    unknown: {
      title: "The model call failed",
      summary: "Something went wrong while generating.",
      tips: ["Retry once.", "Press Test Connection in LLM settings to see whether the engine is reachable.", "Check the terminal window that runs Mørkyn for the full error."],
    },
  };

  const OFFLINE_NARRATOR = {
    kind: "turn_fallback",
    label: "Continue anyway",
    note: "This turn will be written by the offline narrator: short, deterministic prose with no model. The world still moves. You can Rewrite the turn once the model is back.",
  };

  function classify(text, stage = "turn") {
    const raw = String(text || "").trim();
    const low = raw.toLowerCase();
    let code = "unknown";
    for (const [candidate, markers] of RULES) {
      if (markers.some((m) => low.includes(m))) {
        code = candidate;
        break;
      }
    }
    if (code === "unknown" && /\b(401|403)\b/.test(raw)) code = "auth";
    const copy = COPY[code] || COPY.unknown;
    return {
      code,
      stage,
      title: copy.title,
      summary: copy.summary,
      tips: copy.tips.slice(),
      detail: raw.slice(0, 600),
      actions: [{ id: "retry", label: "Retry" }, { id: "settings", label: "Open LLM settings" }],
      fallback: stage === "turn" ? { ...OFFLINE_NARRATOR } : null,
    };
  }

  function parseError(raw, stage = "turn") {
    const text = raw instanceof Error ? raw.message : String(raw || "");
    try {
      const data = JSON.parse(text);
      const detail = data?.detail ?? data;
      if (detail && typeof detail === "object" && detail.problem) {
        return { message: String(detail.message || detail.problem.summary || ""), problem: detail.problem };
      }
      if (typeof detail === "string") return { message: detail, problem: classify(detail, stage) };
    } catch (_) {
      /* plain text */
    }
    return { message: text, problem: classify(text, stage) };
  }

  /* ---- the dialog ---------------------------------------------------------- */

  let modal = null;
  let resolver = null;
  let returnFocus = null;
  const recent = new Map();

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "failsafeModal";
    modal.className = "modalBackdrop failsafeBackdrop hidden";
    modal.setAttribute("role", "alertdialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "failsafeTitle");
    modal.innerHTML = `
      <section class="modalPanel failsafePanel">
        <header class="modalHeader">
          <div>
            <p class="failsafeEyebrow" id="failsafeEyebrow">Model problem</p>
            <h2 id="failsafeTitle"></h2>
            <p id="failsafeSummary"></p>
          </div>
        </header>
        <div class="failsafeBody">
          <h3 class="settingsSubhead">What you can try</h3>
          <ul id="failsafeTips" class="failsafeTips"></ul>
          <details class="failsafeDetail"><summary>Technical detail</summary><pre id="failsafeDetailText"></pre></details>
          <p id="failsafeNote" class="failsafeNote" hidden></p>
        </div>
        <div class="failsafeActions" id="failsafeActions"></div>
      </section>`;
    document.body.append(modal);
    modal.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-choice]");
      if (btn) settle(btn.dataset.choice);
      else if (event.target === modal) settle("dismiss"); // the dark backdrop
    });
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        settle("dismiss");
      }
    });
    return modal;
  }

  function render(problem, { allowFallback = true, title = "" } = {}) {
    const el = ensureModal();
    const p = problem || classify("");
    el.querySelector("#failsafeEyebrow").textContent = title || (p.stage === "load" ? "Model did not load" : p.stage === "runtime" ? "Model status" : "Turn stopped");
    el.querySelector("#failsafeTitle").textContent = p.title || "The model call failed";
    el.querySelector("#failsafeSummary").textContent = p.summary || "";
    el.querySelector("#failsafeTips").innerHTML = (p.tips || []).map((t) => `<li>${esc(t)}</li>`).join("") || "<li>Retry once.</li>";
    const detail = el.querySelector(".failsafeDetail");
    detail.hidden = !p.detail;
    detail.open = false;
    el.querySelector("#failsafeDetailText").textContent = p.detail || "";
    const note = el.querySelector("#failsafeNote");
    const fallback = allowFallback ? p.fallback : null;
    note.hidden = !fallback?.note;
    note.textContent = fallback?.note || "";
    const buttons = [];
    if (fallback) buttons.push(`<button type="button" class="primaryButton failsafePrimary" data-choice="fallback">${esc(fallback.label || "Continue anyway")}</button>`);
    const ids = new Set((p.actions || []).map((a) => a.id));
    if (ids.has("retry") || !p.actions?.length) buttons.push(`<button type="button" data-choice="retry">Retry</button>`);
    if (ids.has("settings") || !p.actions?.length) buttons.push(`<button type="button" data-choice="settings">Open LLM settings</button>`);
    buttons.push(`<button type="button" class="failsafeQuiet" data-choice="dismiss">${fallback ? "Stop here" : "Dismiss"}</button>`);
    el.querySelector("#failsafeActions").innerHTML = buttons.join("");
    el.classList.remove("hidden");
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    (el.querySelector("button[data-choice]") || el).focus();
  }

  function hide() {
    modal?.classList.add("hidden");
    if (returnFocus && document.contains(returnFocus)) {
      try {
        returnFocus.focus({ preventScroll: true });
      } catch (_) {
        /* fine */
      }
    }
    returnFocus = null;
  }

  function settle(choice) {
    const done = resolver;
    resolver = null;
    hide();
    if (choice === "settings") openSettings();
    done?.(choice);
  }

  function openSettings() {
    const btn =
      document.querySelector("#gameView:not(.hidden) #modelButton") ||
      document.querySelector("#setupView:not(.hidden) #setupModelButton") ||
      document.querySelector("#menuSettings");
    if (btn?.id === "modelButton") {
      document.querySelector("#playMenuToggle")?.click();
      setTimeout(() => btn.click(), 150);
    } else {
      btn?.click();
    }
  }

  async function applyEndpointFallback(fallback) {
    const res = await fetch(fallback.url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data?.ok !== false) return { ok: true };
    const message = data?.detail?.message || data?.error || data?.status?.detail || `HTTP ${res.status}`;
    return { ok: false, problem: data?.problem || data?.status?.problem || classify(message, "load") };
  }

  const NOTICE_QUIET_MS = 10 * 60 * 1000;

  function remember(problem) {
    recent.set(String(problem?.code || "unknown"), Date.now());
  }

  /** Show the problem and wait for the player's choice. */
  function ask(problem, options = {}) {
    if (resolver) settle("dismiss");
    remember(problem);
    render(problem, options);
    return new Promise((resolve) => {
      resolver = async (choice) => {
        if (choice === "fallback" && problem?.fallback?.kind === "endpoint") {
          const result = await applyEndpointFallback(problem.fallback);
          if (result.ok) return resolve("retry");
          // The fallback itself failed: show that problem instead.
          return resolve(await ask(result.problem, options));
        }
        resolve(choice);
      };
    });
  }

  /** A background error: inform, do not block, do not repeat within a minute. */
  function notice(problem) {
    if (!problem) return;
    // While a turn is running its own failure will arrive as an ask(); a
    // background notice on top of it would only be noise.
    if (document.body.classList.contains("aiBusy")) return;
    // One notice per kind of problem per ten minutes, and none for a kind the
    // player has just answered in a turn dialog.
    const key = String(problem.code || "unknown");
    if ((recent.get(key) || 0) > Date.now() - NOTICE_QUIET_MS) return;
    remember(problem);
    if (resolver) return; // a blocking ask is already up
    render(problem, { allowFallback: false, title: "Model status" });
    resolver = () => {};
  }

  function tipsHtml(problem) {
    if (!problem?.tips?.length) return "";
    return `<div class="failsafeInline"><strong>${esc(problem.title || "What you can try")}</strong><ul class="failsafeTips">${problem.tips
      .map((t) => `<li>${esc(t)}</li>`)
      .join("")}</ul></div>`;
  }

  window.MorkynFailsafe = { ask, notice, classify, parseError, tipsHtml, openSettings };
})();
