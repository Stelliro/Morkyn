/* Bookmarks on the play screen (Stell, 2026-10-28): "since mobile cannot pop
 * out tabs, we can use this bookmark like system to let users pull out
 * different pinned tabs ... a little [ or ] on the side ... that when clicked
 * on doesnt do anything, but sliding it out changes their window to a
 * bookmarked window, we should start it out having the character window".
 *
 * A handle on the right edge is slid left to open its window; while a
 * bookmarked window is open, a handle on the left edge is slid right to go
 * back. A tap does nothing (a slide is the gesture), Enter or Space on a
 * focused handle does the same as a slide. The handles show on narrow windows
 * and on touch screens, desktop mode included, beside the pop-out windows a
 * wide screen has: no device loses a way in (CSS: .gameBookmarks). */
(() => {
  const PULL_PX = 48;
  const BOOKMARKS = [
    {
      key: "character",
      label: "Character",
      open: () => window.openCharacterSheet?.("you"),
      close: () => window.closeCharacterSheet?.(),
      isOpen: () => {
        const sheet = document.querySelector("#characterSheetDrawer");
        return Boolean(sheet && !sheet.classList.contains("hidden"));
      },
    },
  ];

  let rail = null;
  let back = null;

  const openMark = () => BOOKMARKS.find((mark) => mark.isOpen());

  // A slide in one direction past PULL_PX runs the action; the handle follows
  // the finger while it is held and springs back after.
  function slidable(handle, direction, action) {
    let start = null;
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      start = { x: event.clientX, y: event.clientY, id: event.pointerId };
      handle.setPointerCapture(event.pointerId);
      handle.classList.add("isPulling");
    });
    handle.addEventListener("pointermove", (event) => {
      if (!start || event.pointerId !== start.id) return;
      const dx = (event.clientX - start.x) * direction;
      handle.style.setProperty("--pull", `${Math.max(0, Math.min(dx, PULL_PX * 1.5))}px`);
    });
    const finish = (event) => {
      if (!start || event.pointerId !== start.id) return;
      const dx = (event.clientX - start.x) * direction;
      const dy = Math.abs(event.clientY - start.y);
      start = null;
      handle.classList.remove("isPulling");
      handle.style.removeProperty("--pull");
      if (event.type === "pointerup" && dx >= PULL_PX && dx > dy) action();
    };
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
    // A tap is not a slide: the click it makes does nothing.
    handle.addEventListener("click", (event) => event.preventDefault());
    handle.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      action();
    });
  }

  function build() {
    rail = document.createElement("div");
    rail.className = "gameBookmarks";
    rail.setAttribute("role", "group");
    rail.setAttribute("aria-label", "Bookmarks: slide one out to open it");
    BOOKMARKS.forEach((mark) => {
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "gameBookmark";
      handle.dataset.bookmark = mark.key;
      handle.setAttribute("aria-label", `${mark.label}: slide out to open`);
      handle.innerHTML = `<span class="gameBookmarkGlyph" aria-hidden="true">[</span><span class="gameBookmarkLabel">${mark.label}</span>`;
      slidable(handle, -1, () => {
        mark.open();
        refresh();
      });
      rail.appendChild(handle);
    });
    back = document.createElement("button");
    back.type = "button";
    back.className = "gameBookmark gameBookmarkBack";
    back.setAttribute("aria-label", "Slide back to the game");
    back.innerHTML = `<span class="gameBookmarkGlyph" aria-hidden="true">]</span><span class="gameBookmarkLabel">Game</span>`;
    slidable(back, 1, () => {
      openMark()?.close();
      refresh();
    });
    document.body.append(rail, back);
  }

  // The handles belong to the play screen: shown only while it is up.
  function refresh() {
    if (!rail) return;
    const game = document.querySelector("#gameView");
    const playing = Boolean(game && !game.classList.contains("hidden"));
    const open = openMark();
    rail.hidden = !playing || Boolean(open);
    back.hidden = !playing || !open;
  }

  function boot() {
    build();
    refresh();
    const watch = new MutationObserver(refresh);
    ["#gameView", "#characterSheetDrawer"].forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) watch.observe(el, { attributes: true, attributeFilter: ["class"] });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.MorkynBookmarks = { refresh, list: () => BOOKMARKS.map((mark) => mark.key) };
})();
