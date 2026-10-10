/* ==========================================================================
   Mørkyn UI · death.js  (the "You died" screen)

   The engine records a death in state.dead (app/world.py _record_death) and
   returns it beside the death turn (payload.dead). This module shows the
   screen: after the death turn's prose (app.js displayTurnPayload), when a
   dead save is opened (renderShell), and when a turn is refused because the
   story has ended (requestTurn). It never mentions the graveyard copy an
   ironman death leaves in data/: that is for the player's own sake.

   Classic script loaded after app.js; relies on its globals showMainMenu,
   openSaveBrowser and refreshContinueButton, each call guarded. Layout lives in
   styles.css ("death" block), look in skin.css.
   ========================================================================== */
(function () {
  "use strict";

  let modal = null;
  let shownKey = "";

  function esc(text) {
    return String(text ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  }

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "deathModal";
    modal.className = "modalBackdrop deathBackdrop hidden";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "deathTitle");
    modal.innerHTML = `
      <section class="modalPanel deathPanel">
        <p class="deathEyebrow" id="deathEyebrow">The story ends</p>
        <h2 class="deathTitle" id="deathTitle">You died</h2>
        <p class="deathWho" id="deathWho"></p>
        <p class="deathCause" id="deathCause"></p>
        <div class="deathFacts" id="deathFacts"></div>
        <p class="deathNote" id="deathNote"></p>
        <div class="deathActions" id="deathActions"></div>
      </section>`;
    document.body.append(modal);
    modal.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-choice]");
      if (btn) choose(btn.dataset.choice, btn);
    });
    return modal;
  }

  function facts(dead) {
    const out = [];
    if (dead.day) out.push(`Day ${esc(dead.day)}${dead.time_label ? ` · ${esc(String(dead.time_label).split("·").pop().trim())}` : ""}`);
    if (Number.isFinite(Number(dead.turns_survived))) out.push(`${esc(dead.turns_survived)} turn${Number(dead.turns_survived) === 1 ? "" : "s"} survived`);
    if (dead.location) out.push(esc(dead.location));
    if (dead.level) out.push(`Level ${esc(dead.level)}`);
    return out.map((f) => `<span>${f}</span>`).join("");
  }

  function render(dead) {
    const el = ensureModal();
    const ironman = Boolean(dead.ironman || dead.rule === "ironman");
    const name = [dead.player_name, dead.title].filter(Boolean).join(", ");
    el.querySelector("#deathEyebrow").textContent = ironman ? "One life" : "The story ends";
    el.querySelector("#deathWho").textContent = name;
    el.querySelector("#deathCause").textContent = dead.cause || dead.last_words || "";
    el.querySelector("#deathFacts").innerHTML = facts(dead);
    el.querySelector("#deathNote").textContent = ironman
      ? "The road closes behind you. Whoever comes next starts from nothing."
      : "Your earlier saves are still there. The autosave remembers the end.";
    const buttons = [];
    if (!ironman) buttons.push(`<button type="button" class="primaryButton" data-choice="load">Load a save</button>`);
    buttons.push(`<button type="button" class="${ironman ? "primaryButton" : ""}" data-choice="new">${ironman ? "Begin again" : "Main menu"}</button>`);
    el.querySelector("#deathActions").innerHTML = buttons.join("");
    el.classList.remove("hidden");
    (el.querySelector("button[data-choice]") || el).focus();
  }

  function hide() {
    modal?.classList.add("hidden");
  }

  function choose(choice, button) {
    hide();
    try {
      window.showMainMenu?.();
      window.refreshContinueButton?.();
    } catch (_) {
      /* the menu is still reachable */
    }
    if (choice === "load") {
      try {
        window.openSaveBrowser?.("load", button);
        return;
      } catch (_) {
        /* fall through to the menu */
      }
    }
    document.querySelector("#menuNewGame")?.focus();
  }

  /**
   * Show the screen for a death record. Each record shows once (keyed on its
   * timestamp and turn) unless force is set, so a redraw of the shell does not
   * flash it again over a screen the player already read.
   */
  function show(dead, options = {}) {
    if (!dead || typeof dead !== "object") return false;
    const key = `${dead.at || ""}|${dead.turn || ""}|${dead.player_name || ""}`;
    if (!options.force && key === shownKey && modal && !modal.classList.contains("hidden")) return false;
    shownKey = key;
    render(dead);
    return true;
  }

  window.MorkynDeath = { show, hide };
})();
