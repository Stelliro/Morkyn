/* The in-game tour (Stell, 2026-10-28: "we just need to show players were
 * things are ... we dont want it long, but we do want it to be informative").
 * A spotlight on each part of the play screen, once, the first time the game
 * view opens; Settings can replay it. A step whose part is hidden (a panel
 * the player closed, a phone layout) is skipped. */
(() => {
  const SEEN_KEY = "morkyn-game-tour-v1";
  const STEPS = [
    {
      sel: "#latestOutput",
      title: "The story",
      text: "Each turn's scene is written here. Coloured names are people, places and items: click one to see what the game knows about it.",
    },
    {
      sel: "#turnInput",
      title: "What you do",
      text: "Write what you do or say in your own words, then press Send. Only you decide what your character does.",
    },
    {
      sel: ".composerActionsMain",
      title: "Turn buttons",
      text: "Continue lets the scene go on without an action. Wait spends time (rest, sleep, until dawn). Undo last turn takes a turn back; Rewrite writes the last turn's scene again. Ideas suggests things to try.",
    },
    {
      sel: "#askButton",
      title: "Ask, no turn",
      text: "Type a question in the box and press this to look something up. No time passes. Help, beside it, lists links and commands.",
    },
    {
      sel: "#talkTargetButton",
      title: "Talking to",
      text: "Pick who your words are aimed at when several people are here.",
    },
    {
      sel: "#sceneHistoryToggle",
      title: "History",
      text: "Shows earlier turns above this one. Side hides or shows the panel on the right.",
    },
    {
      sel: "#mapViewBar",
      title: "Map",
      text: "The world around you, who is here, or the large map. Walk one tile with the Move pad or the arrow keys.",
    },
    {
      sel: ".dockYou",
      title: "You",
      text: "Your health, money and level at a glance.",
    },
    {
      sel: "section[aria-labelledby='whoIsHereHeading']",
      title: "Who is here",
      text: "The people at your place. Hover a name to peek, Details for their record, right-click for actions.",
    },
    {
      sel: "section[aria-labelledby='mapPackHeading']",
      title: "Pack",
      text: "What you carry and wear.",
    },
    // Device-specific: each shows only where its part is on screen.
    {
      sel: ".gameBookmarks .gameBookmark",
      title: "Bookmarks",
      text: "Slide this handle out from the edge to open your character. A tap does nothing, so it never opens by accident. To come back, slide the handle on the left edge.",
    },
    {
      sel: ".popHint.popWindow",
      title: "Pop out",
      text: "Opens this panel in its own window, so you can keep it beside the game.",
    },
    {
      sel: "#playMenuToggle",
      title: "Menu",
      text: "Your character sheet, people, world notes, quests, history and tools. Saving, settings and the main menu are here too.",
    },
  ];

  let index = -1;
  let layer = null;

  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    const box = el.getBoundingClientRect();
    if (box.width < 2 || box.height < 2) return false;
    return getComputedStyle(el).visibility !== "hidden";
  };

  function build() {
    if (layer) return layer;
    layer = document.createElement("div");
    layer.id = "gameTour";
    layer.className = "gameTour";
    layer.hidden = true;
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-modal", "true");
    layer.setAttribute("aria-labelledby", "gameTourTitle");
    layer.innerHTML = `
      <div class="gameTourSpot" aria-hidden="true"></div>
      <div class="gameTourCard">
        <p class="gameTourMeta"></p>
        <h2 id="gameTourTitle" class="gameTourTitle"></h2>
        <p class="gameTourText"></p>
        <div class="gameTourActions">
          <button type="button" class="chipBtn" data-game-tour="skip">Skip</button>
          <button type="button" class="chipBtn" data-game-tour="back">Back</button>
          <button type="button" class="primaryButton" data-game-tour="next">Next</button>
        </div>
      </div>`;
    document.body.appendChild(layer);
    layer.addEventListener("click", (event) => {
      const act = event.target.closest("[data-game-tour]")?.dataset.gameTour;
      if (act === "next") go(1);
      else if (act === "back") go(-1);
      else if (act === "skip") end();
    });
    return layer;
  }

  // The steps whose part is on screen now, in order.
  function liveSteps() {
    return STEPS.map((step) => ({ ...step, el: document.querySelector(step.sel) })).filter((step) => visible(step.el));
  }

  function place() {
    if (!layer || layer.hidden) return;
    const steps = liveSteps();
    const step = steps[index];
    if (!step) return;
    const spot = layer.querySelector(".gameTourSpot");
    const card = layer.querySelector(".gameTourCard");
    const pad = 6;
    const box = step.el.getBoundingClientRect();
    const top = Math.max(4, box.top - pad);
    const left = Math.max(4, box.left - pad);
    const bottom = Math.min(window.innerHeight - 4, box.bottom + pad);
    const right = Math.min(window.innerWidth - 4, box.right + pad);
    Object.assign(spot.style, { top: `${top}px`, left: `${left}px`, width: `${right - left}px`, height: `${bottom - top}px` });
    // The card goes below the part, or above it, or beside it, whichever fits.
    const cw = card.offsetWidth;
    const ch = card.offsetHeight;
    const gap = 12;
    let y;
    let x = Math.min(Math.max(8, left), window.innerWidth - cw - 8);
    if (bottom + gap + ch <= window.innerHeight - 8) y = bottom + gap;
    else if (top - gap - ch >= 8) y = top - gap - ch;
    else {
      y = Math.min(Math.max(8, top), window.innerHeight - ch - 8);
      x = right + gap + cw <= window.innerWidth - 8 ? right + gap : Math.max(8, left - gap - cw);
    }
    Object.assign(card.style, { top: `${y}px`, left: `${x}px` });
  }

  function show() {
    const steps = liveSteps();
    if (!steps.length) return end();
    index = Math.max(0, Math.min(index, steps.length - 1));
    const step = steps[index];
    build();
    layer.hidden = false;
    step.el.scrollIntoView({ block: "nearest" });
    layer.querySelector(".gameTourMeta").textContent = `Step ${index + 1} of ${steps.length}`;
    layer.querySelector(".gameTourTitle").textContent = step.title;
    layer.querySelector(".gameTourText").textContent = step.text;
    layer.querySelector("[data-game-tour='back']").disabled = index === 0;
    const next = layer.querySelector("[data-game-tour='next']");
    next.textContent = index === steps.length - 1 ? "Finish" : "Next";
    place();
    next.focus({ preventScroll: true });
  }

  function go(delta) {
    const count = liveSteps().length;
    if (delta > 0 && index >= count - 1) return end();
    index = Math.max(0, index + delta);
    show();
  }

  function start() {
    index = 0;
    show();
  }

  function end() {
    if (layer) layer.hidden = true;
    index = -1;
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch (_) {
      /* private mode: the tour may show again next time */
    }
  }

  function seen() {
    try {
      return localStorage.getItem(SEEN_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function reset() {
    try {
      localStorage.removeItem(SEEN_KEY);
    } catch (_) {
      /* ignore */
    }
  }

  document.addEventListener(
    "keydown",
    (event) => {
      if (!layer || layer.hidden) return;
      // Enter and Space press the focused tour button on their own.
      if (event.key === "Escape") end();
      else if (event.key === "ArrowRight") go(1);
      else if (event.key === "ArrowLeft") go(-1);
      else return;
      event.preventDefault();
      event.stopImmediatePropagation();
    },
    true,
  );
  window.addEventListener("resize", place);
  document.addEventListener("scroll", place, true);

  // First run: once the play screen is on show and nothing else is open over it.
  function maybeStart() {
    if (seen() || (layer && !layer.hidden)) return;
    const game = document.querySelector("#gameView");
    if (!game || game.classList.contains("hidden")) return;
    setTimeout(() => {
      const busy = document.querySelector(".modalBackdrop:not(.hidden), #playMenuDrawer:not(.hidden)");
      if (seen() || busy || game.classList.contains("hidden") || (layer && !layer.hidden)) return;
      start();
    }, 1200);
  }
  function boot() {
    const game = document.querySelector("#gameView");
    if (!game) return;
    new MutationObserver(maybeStart).observe(game, { attributes: true, attributeFilter: ["class"] });
    maybeStart();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.MorkynGameTour = { start, end, reset, seen };
})();
