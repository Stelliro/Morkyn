/* ==========================================================================
   Mørkyn UI · interact.js  (behaviour layer)

   Four small systems that make the interface denser without changing what
   app.js renders:

     1. Folds     any section heading in the lists below collapses the block
                  under it; the choice is remembered per screen in localStorage
                  and re-applied after every re-render.
     2. Peeks     hovering a name (an NPC, item, place, event, skill, ability)
                  shows a translucent card with the short version. Click still
                  opens the full details; the card never traps the pointer.
     3. Context   right-click (or Shift+F10 / long-press) on a name opens a
                  menu of actions. Most actions put a sentence into "What will
                  you do?" and leave the player to press Send; the ones that
                  act immediately say so in their label.
     4. Provider  the LLM and app settings forms show only the fields that
                  belong to the selected provider.

   This is a classic script loaded after app.js and relies on its globals:
   getEntityMap, entityLabel, showEntity, insertRef, insertRawToken,
   inventoryRowIndex, itemOverlayHtml, positionFloatingOverlay, escapeHtml,
   enqueueAiTask, requestTurn, _watchedNpcIds, refreshLocalMap, activeTab.
   Every call is guarded, so a renamed global degrades to "feature off",
   not a broken page.

   Layout for the elements it creates lives in styles.css ("interact" block);
   their look lives in ui/skin.css section 12. Rulebook: docs/UI_RULEBOOK.md §3.7
   ========================================================================== */

(function () {
  "use strict";

  const has = (name) => typeof window[name] === "function";
  // app.js declares some state with let/const, which lives in the global
  // lexical scope but not on window. Read those by bare name, guarded.
  const liveTab = () => (typeof activeTab === "string" ? activeTab : "");
  const liveInventory = () => (typeof inventoryRowIndex !== "undefined" && inventoryRowIndex instanceof Map ? inventoryRowIndex : null);
  const liveWatched = () => (typeof _watchedNpcIds !== "undefined" && _watchedNpcIds instanceof Set ? _watchedNpcIds : null);
  const esc = (value) =>
    has("escapeHtml")
      ? window.escapeHtml(value)
      : String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const label = (entity) => (has("entityLabel") ? window.entityLabel(entity) : entity?.name || entity?.code || "");
  const clip = (text, max) => {
    const s = String(text || "").replace(/\s+/g, " ").trim();
    return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s;
  };

  /* ------------------------------------------------------------------------
     1. Folds
     ------------------------------------------------------------------------ */

  const FOLD_STORE = "morkyn-ui-folds-v1";
  const FOLD_HEADINGS = ".settingsSubhead, .mapSectionTitle, .characterSheetSectionTitle, .saveEditorHeading, .setupFactGroupHead > h2, .sectionHeader .sectionHeaderTitle";
  const FOLD_STOP = `${FOLD_HEADINGS}, .setupFactGroupHead, .sectionHeader`;
  const FOLD_SCOPES = "#indexContent, #mapColumnList, #characterSheetBody, #setupView, #modelModalContent, #appSettingsModal, #saveBrowserBody, #entityMenu";

  let folds = {};
  try {
    folds = JSON.parse(localStorage.getItem(FOLD_STORE) || "{}") || {};
  } catch (_) {
    folds = {};
  }
  const saveFolds = () => {
    try {
      localStorage.setItem(FOLD_STORE, JSON.stringify(folds));
    } catch (_) {
      /* private mode: folds last for the session */
    }
  };

  function foldAnchor(heading) {
    return heading.closest(".setupFactGroupHead, .sectionHeader") || heading;
  }

  // A heading may ask to start closed (data-fold-default="closed"); a stored
  // choice always wins. While the first-run tour is pointing at fields,
  // nothing is folded, or the spotlight would land on a hidden element.
  function tourShowing() {
    return Boolean(document.querySelector("#setupTourLayer:not(.hidden)"));
  }

  function wantsFolded(heading) {
    const key = foldKey(heading);
    if (key in folds) return Boolean(folds[key]);
    return heading.dataset.foldDefault === "closed";
  }

  function foldKey(heading) {
    const scope = heading.closest(FOLD_SCOPES);
    let id = scope?.id || "page";
    if (id === "indexContent" && liveTab()) id += `/${liveTab()}`;
    return `${id}|${clip(heading.textContent, 60)}`;
  }

  function foldRegion(heading) {
    const out = [];
    let node = foldAnchor(heading).nextElementSibling;
    while (node) {
      if (node.matches(FOLD_STOP)) break;
      out.push(node);
      node = node.nextElementSibling;
    }
    return out;
  }

  function applyFold(heading, folded) {
    const region = foldRegion(heading);
    if (!region.length) return false;
    region.forEach((el) => el.classList.toggle("uiFolded", folded));
    heading.classList.toggle("isFolded", folded);
    heading.setAttribute("aria-expanded", folded ? "false" : "true");
    return true;
  }

  function applyFolds(root = document) {
    const tour = tourShowing();
    root.querySelectorAll(FOLD_HEADINGS).forEach((heading) => {
      if (!foldRegion(heading).length) return;
      if (!heading.classList.contains("isFoldable")) {
        heading.classList.add("isFoldable");
        heading.setAttribute("role", "button");
        if (!heading.hasAttribute("tabindex")) heading.tabIndex = 0;
        heading.title = heading.title || "Click to fold or unfold";
      }
      applyFold(heading, tour ? false : wantsFolded(heading));
    });
  }

  function toggleFold(heading) {
    const key = foldKey(heading);
    const next = !heading.classList.contains("isFolded");
    folds[key] = next;
    saveFolds();
    applyFold(heading, next);
  }

  document.addEventListener("click", (event) => {
    const heading = event.target.closest?.(FOLD_HEADINGS);
    if (!heading || !heading.classList.contains("isFoldable")) return;
    // A control inside the heading (a button, a link) keeps its own job.
    const control = event.target.closest("button, a, input, select, textarea, label");
    if (control && heading.contains(control) && control !== heading) return;
    event.preventDefault();
    toggleFold(heading);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const heading = event.target.closest?.(FOLD_HEADINGS);
    if (!heading || !heading.classList.contains("isFoldable") || event.target !== heading) return;
    event.preventDefault();
    toggleFold(heading);
  });

  /* ------------------------------------------------------------------------
     4. Provider-aware forms (declared early; applied by the same observer)
     ------------------------------------------------------------------------ */

  const PROVIDER_FORMS = [
    {
      form: "#modelForm",
      select: '[name="provider"]',
      fields: {
        llama_cpp: ["gguf_model_path", "llama_cpp_base_url"],
        mle: ["mle_model"],
        openai: ["api_preset", "api_base_url", "api_model", "api_key"],
      },
    },
    {
      form: "#appSettingsModal form, #appSettingsForm",
      select: '[name="model_provider"]',
      fields: {
        llama_cpp: ["gguf_model_path"],
        mle: ["mle_model"],
        openai: ["api_base_url", "api_model"],
      },
    },
  ];

  function applyProviderFields(root = document) {
    PROVIDER_FORMS.forEach((spec) => {
      root.querySelectorAll(spec.form).forEach((form) => {
        const select = form.querySelector(spec.select);
        const show = select && spec.fields[select.value];
        if (!show) return;
        const all = new Set(Object.values(spec.fields).flat());
        all.forEach((name) => {
          const input = form.querySelector(`[name="${name}"]`);
          const row = input?.closest("label, .settingField, .appSettingsField");
          if (row) row.classList.toggle("uiOffProvider", !show.includes(name));
        });
      });
    });
  }

  document.addEventListener("change", (event) => {
    const select = event.target;
    if (!(select instanceof HTMLSelectElement)) return;
    if (!PROVIDER_FORMS.some((spec) => select.matches(spec.select) && select.closest(spec.form))) return;
    applyProviderFields();
  });

  /* ------------------------------------------------------------------------
     Shared: turn an element into {type, entity, code}
     ------------------------------------------------------------------------ */

  function resolve(el) {
    if (!el || !has("getEntityMap")) return null;
    const invKey = el.closest("[data-inv-key]")?.dataset.invKey;
    const inventory = liveInventory();
    if (invKey && inventory) {
      const item = inventory.get(invKey);
      if (item) return { type: "item", entity: item, code: String(item.code || "") };
    }
    let code =
      el.closest("[data-code]")?.dataset.code ||
      el.closest("[data-link-code]")?.dataset.linkCode ||
      el.closest("[data-npc-code]")?.dataset.npcCode ||
      "";
    if (!code) {
      const card = el.closest(".castCard, .miniItem, .entityCard");
      const inner = card?.querySelector("[data-code], [data-npc-code]");
      code = inner?.dataset.code || inner?.dataset.npcCode || "";
      if (!code && card?.dataset.linkToken) {
        const match = String(card.dataset.linkToken).match(/\[\[([A-Za-z]+\d*)\]\]/);
        code = match ? match[1] : "";
      }
    }
    if (!code) return null;
    const found = window.getEntityMap().get(String(code).toUpperCase());
    if (!found?.entity) return null;
    return { type: found.type, entity: found.entity, code: String(found.entity.code || code) };
  }

  /* ------------------------------------------------------------------------
     2. Peeks
     ------------------------------------------------------------------------ */

  const PEEK_ANCHORS = ".entityLink[data-code]:not(.unresolved), .castCard, .miniItem:not(.miniItemMore), .castDetailsBtn, .miniDetailsBtn, .entityCard[data-link-token]";
  const PEEK_DELAY = 220;
  let peekEl = null;
  let peekTarget = null;
  let peekTimer = 0;

  function peek() {
    if (peekEl) return peekEl;
    peekEl = document.createElement("div");
    peekEl.id = "uiPeek";
    peekEl.className = "uiPeek hidden";
    peekEl.setAttribute("role", "tooltip");
    document.body.append(peekEl);
    return peekEl;
  }

  function peekHtml(found) {
    const { type, entity, code } = found;
    const name = label(entity);
    const hint = `<p class="uiPeekHint">Click for details · Right-click for actions</p>`;
    if (type === "item" && has("itemOverlayHtml")) return window.itemOverlayHtml(entity) + hint;
    let meta = [];
    let desc = "";
    if (type === "npc") {
      meta = [entity.race || "human", entity.role, entity.rank ? `rank ${entity.rank}` : "", entity.attitude, entity.trust != null ? `trust ${entity.trust}` : ""];
      desc = entity.summary;
    } else if (type === "location") {
      meta = [entity.visit_count != null ? `${entity.visit_count} visit${entity.visit_count === 1 ? "" : "s"}` : "", entity.npcs?.length ? `${entity.npcs.length} people` : ""];
      desc = entity.summary;
    } else if (type === "event") {
      meta = [entity.status, entity.location_code];
      desc = entity.summary;
    } else if (type === "skill") {
      meta = [entity.value != null ? `value ${entity.value}` : ""];
      desc = entity.notes || entity.description || entity.summary;
    } else if (type === "ability") {
      meta = [entity.power_type || "ability"];
      desc = entity.description;
    } else {
      desc = entity.description || entity.summary;
    }
    meta = meta.filter(Boolean);
    return `
      <header class="uiPeekHead"><strong>${esc(name)}</strong><span class="uiPeekKind">${esc(type)} · ${esc(code)}</span></header>
      ${meta.length ? `<p class="uiPeekMeta">${meta.map(esc).join(" · ")}</p>` : ""}
      ${desc ? `<p class="uiPeekDesc">${esc(clip(desc, 240))}</p>` : ""}
      ${hint}`;
  }

  function showPeek(target) {
    const found = resolve(target);
    if (!found || !has("positionFloatingOverlay")) return;
    const el = peek();
    el.innerHTML = peekHtml(found);
    el.classList.toggle("itemHoverOverlay", found.type === "item");
    peekTarget = target;
    window.positionFloatingOverlay(el, target);
  }

  function hidePeek() {
    clearTimeout(peekTimer);
    peekTimer = 0;
    peekTarget = null;
    peekEl?.classList.add("hidden");
  }

  // A scroll moves the anchor, so a visible peek must go; a pending one may
  // still appear, at the anchor's new place, when the timer fires.
  function hideVisiblePeek() {
    if (!peekTarget) return;
    peekTarget = null;
    peekEl?.classList.add("hidden");
  }

  document.addEventListener("pointerover", (event) => {
    if (event.pointerType === "touch") return;
    // Inventory rows have their own, fuller overlay in app.js.
    if (event.target.closest?.("[data-inv-key]")) return;
    const anchor = event.target.closest?.(PEEK_ANCHORS);
    if (!anchor) {
      if (peekTarget) hidePeek();
      return;
    }
    if (anchor === peekTarget || menuOpen) return;
    clearTimeout(peekTimer);
    peekTimer = setTimeout(() => showPeek(anchor), PEEK_DELAY);
  });
  document.addEventListener("pointerout", (event) => {
    const anchor = event.target.closest?.(PEEK_ANCHORS);
    if (!anchor) return;
    const next = event.relatedTarget;
    if (next && anchor.contains(next)) return;
    hidePeek();
  });
  document.addEventListener("scroll", hideVisiblePeek, true);
  window.addEventListener("resize", hidePeek);
  document.addEventListener("click", hidePeek, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hidePeek();
  });

  /* ------------------------------------------------------------------------
     3. Context menu
     ------------------------------------------------------------------------ */

  const MENU_ANCHORS = ".entityLink[data-code]:not(.unresolved), [data-inv-key], .castCard, .miniItem:not(.miniItemMore), .castDetailsBtn, .miniDetailsBtn, .entityCard[data-link-token], .slotWornItem";
  let menuEl = null;
  let menuOpen = false;
  let menuReturn = null;

  function menu() {
    if (menuEl) return menuEl;
    menuEl = document.createElement("div");
    menuEl.id = "uiContextMenu";
    menuEl.className = "uiContextMenu hidden";
    menuEl.setAttribute("role", "menu");
    document.body.append(menuEl);
    menuEl.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) return;
      const run = menuActions[Number(btn.dataset.action)];
      closeMenu();
      try {
        run?.();
      } catch (error) {
        console.error("context action failed:", error);
      }
    });
    menuEl.addEventListener("keydown", (event) => {
      const items = [...menuEl.querySelectorAll("button[data-action]")];
      const at = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        items[(at + step + items.length) % items.length]?.focus();
      } else if (event.key === "Escape" || event.key === "Tab") {
        event.preventDefault();
        closeMenu(true);
      }
    });
    return menuEl;
  }

  let menuActions = [];

  function insert(text) {
    return () => {
      if (has("insertRawToken")) window.insertRawToken(text);
    };
  }

  function toggleWatch(entity) {
    const id = String(entity.id);
    fetch(`/api/npc/${encodeURIComponent(id)}/watch`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        const watched = liveWatched();
        if (watched) {
          if (data.watching) watched.add(id);
          else watched.delete(id);
        }
        window.refreshLocalMap?.();
        if (has("renderIndex")) window.renderIndex();
      })
      .catch(() => {});
  }

  function attackNow(code, name) {
    if (!has("enqueueAiTask") || !has("requestTurn")) return;
    window
      .enqueueAiTask(() => window.requestTurn(`attack ${name} [[${code}]]`, { displayText: `⚔ Attack ${name}` }), `Starting fight with ${name}…`)
      .catch((error) => console.error("attack failed:", error));
  }

  function buildActions(found) {
    const { type, entity, code } = found;
    const name = label(entity);
    const ref = code ? ` [[${code}]]` : "";
    const items = [];
    if (code && has("showEntity")) items.push({ text: "Details", run: () => window.showEntity(code) });
    if (code && has("insertRef")) items.push({ text: "Link into input", run: () => window.insertRef(type, code) });
    if (type === "npc") {
      items.push({ text: `Talk to ${name}`, run: insert(`talk to ${name}${ref}`) });
      items.push({ text: `Ask ${name} about…`, run: insert(`ask ${name}${ref} about `) });
      if (entity.id != null) {
        const watched = Boolean(liveWatched()?.has(String(entity.id)));
        items.push({ text: watched ? "Unpin from map" : "Pin on map", run: () => toggleWatch(entity) });
      }
      items.push({ text: `Attack ${name} now`, danger: true, run: () => attackNow(code, name) });
    } else if (type === "item") {
      items.push({ text: "Examine", run: insert(`examine ${name}${ref}`) });
      items.push(entity.equipped_slot ? { text: "Unequip", run: insert(`unequip ${name}${ref}`) } : { text: "Equip", run: insert(`equip ${name}${ref}`) });
      items.push({ text: "Use", run: insert(`use ${name}${ref}`) });
      items.push({ text: "Drop", danger: true, run: insert(`drop ${name}${ref}`) });
    } else if (type === "location") {
      items.push({ text: `Go to ${name}`, run: insert(`go to ${name}${ref}`) });
      items.push({ text: "Who is here", run: () => document.querySelector("#whoIsHereJump")?.click() });
    } else if (type === "skill" || type === "ability") {
      items.push({ text: `Use ${name}`, run: insert(`use ${name}${ref}`) });
    } else if (type === "event") {
      items.push({ text: "Look into it", run: insert(`look into ${name}${ref}`) });
    }
    if (navigator.clipboard?.writeText) items.push({ text: "Copy name", run: () => navigator.clipboard.writeText(name).catch(() => {}) });
    return { name, type, items };
  }

  function openMenu(found, x, y, anchor) {
    openMenuWith(buildActions(found), x, y, anchor);
  }

  function openMenuWith({ name, type, items }, x, y, anchor) {
    if (!items.length) return;
    hidePeek();
    const el = menu();
    menuActions = items.map((item) => item.run);
    el.innerHTML = `
      <header><strong>${esc(name)}</strong><span>${esc(type)}</span></header>
      ${items.map((item, i) => `<button type="button" role="menuitem" data-action="${i}"${item.danger ? ' class="isDanger"' : ""}>${esc(item.text)}</button>`).join("")}`;
    el.classList.remove("hidden");
    const box = el.getBoundingClientRect();
    const margin = 8;
    el.style.left = `${Math.max(margin, Math.min(x, window.innerWidth - box.width - margin))}px`;
    el.style.top = `${Math.max(margin, Math.min(y, window.innerHeight - box.height - margin))}px`;
    menuOpen = true;
    menuReturn = anchor instanceof HTMLElement ? anchor : null;
    el.querySelector("button[data-action]")?.focus();
  }

  function closeMenu(refocus = false) {
    if (!menuOpen) return;
    menuOpen = false;
    menuEl?.classList.add("hidden");
    menuActions = [];
    if (refocus && menuReturn && document.contains(menuReturn)) {
      try {
        menuReturn.focus({ preventScroll: true });
      } catch (_) {
        /* fine */
      }
    }
    menuReturn = null;
  }

  /* ------------------------------------------------------------------------
     3b. The map canvases. app.js draws two: #playMapCanvas (the lens beside
     the scene) and #fullMapCanvas (the world map overlay). Both leave their
     grid on canvas._mapMeta {cell, minX, minY} and their data on a view
     object, so a pointer position becomes a tile the same way the click
     handlers do it.
     ------------------------------------------------------------------------ */

  const MAP_CANVASES = "#playMapCanvas, #fullMapCanvas";

  function mapView(canvas) {
    if (canvas.id === "playMapCanvas") return typeof localMapView !== "undefined" ? localMapView : null;
    return typeof fullMapView !== "undefined" ? fullMapView : null;
  }

  function tileAt(canvas, event) {
    const meta = canvas._mapMeta;
    const view = mapView(canvas);
    if (!meta || !view) return null;
    const rect = canvas.getBoundingClientRect();
    const cell = meta.cell || (typeof mapTilePx !== "undefined" ? mapTilePx : 32) || 32;
    const px = Number(view.player?.x ?? 0);
    const py = Number(view.player?.y ?? 0);
    // The lens ("local" mode) keeps its grid relative to the player, who sits
    // at (0,0); tiles and the player themselves are absolute. The world map
    // keeps everything absolute.
    const relative = meta.mode === "local";
    const cx = Math.floor(((event.clientX - rect.left) * (canvas.width / rect.width)) / cell) + Number(meta.minX || 0) + (relative ? px : 0);
    const cy = Math.floor(((event.clientY - rect.top) * (canvas.height / rect.height)) / cell) + Number(meta.minY || 0) + (relative ? py : 0);
    const full = typeof fullMapView !== "undefined" ? fullMapView : null;
    const at = (list) => (list || []).find((p) => Number(p.x) === cx && Number(p.y) === cy);
    const quests = typeof _lastQuestMarkers !== "undefined" ? _lastQuestMarkers : [];
    return {
      canvas,
      cx,
      cy,
      dx: cx - px,
      dy: cy - py,
      tile: at(view.tiles),
      settle: at(view.settlements || full?.settlements),
      marker: at(view.markers || full?.markers),
      quest: (quests || []).find((qm) => Math.round(Number(qm.coords?.x)) === cx && Math.round(Number(qm.coords?.y)) === cy),
    };
  }

  function tileLabel(t) {
    if (t.quest) return `❗ ${t.quest.quest_name}`;
    if (t.settle) return String(t.settle.name || "Settlement");
    if (t.marker) return String(t.marker.label || "Known place");
    if (!t.dx && !t.dy) return "Where you stand";
    if (!t.tile || (t.tile.fog && !t.tile.visited)) return "Unknown ground";
    return `${t.tile.state || "tile"}${t.tile.visited ? " · visited" : ""}`;
  }

  function mapActions(t) {
    const items = [];
    const here = !t.dx && !t.dy;
    const adjacent = !here && Math.abs(t.dx) <= 1 && Math.abs(t.dy) <= 1;
    if (adjacent && has("walkStep")) {
      // Not silent: a blocked step (a wall, a locked scene) explains itself in the travel banner.
      items.push({ text: "Step here", run: () => window.walkStep(t.dx, t.dy, {}) });
    } else if (!here && has("walkToTile") && !(t.tile && t.tile.walkable === false)) {
      items.push({
        text: "Travel here",
        run: () => {
          // Same gate as a long click: long trips wait for the scene to clear.
          if (typeof travelReady !== "undefined" && !travelReady) {
            // app.js's setTravelBanner owns the banner's words and colour (playtest #61).
            window.setTravelBanner?.("Adjacent steps only while the scene holds long travel.", "refusal", 1600);
            return;
          }
          window.walkToTile(t.cx, t.cy);
        },
      });
    }
    if (here) items.push({ text: "Who is here", run: () => document.querySelector("#whoIsHereJump")?.click() });
    if (t.settle && has("showSettlementDetail")) {
      items.push({ text: `About ${t.settle.name}`, run: () => window.showSettlementDetail(t.settle) });
    } else if (t.marker && has("showSettlementDetail")) {
      const m = t.marker;
      items.push({
        text: `About ${m.label || "this place"}`,
        run: () => window.showSettlementDetail({ x: m.x, y: m.y, name: m.label, state: m.kind, summary: m.summary || `Known from ${m.source || "intel"}.`, kind: m.kind }),
      });
    }
    const placeName = t.settle?.name || t.marker?.label || t.quest?.location_name || "";
    if (placeName) items.push({ text: `Write "go to ${placeName}"`, run: insert(`go to ${placeName}`) });
    if (t.quest) items.push({ text: `Write "work on ${t.quest.quest_name}"`, run: insert(`work on ${t.quest.quest_name}`) });
    if (t.canvas.id === "playMapCanvas" && has("openMapOverlay")) items.push({ text: "Open world map", run: () => window.openMapOverlay() });
    if (navigator.clipboard?.writeText) items.push({ text: `Copy (${t.cx}, ${t.cy})`, run: () => navigator.clipboard.writeText(`${t.cx},${t.cy}`).catch(() => {}) });
    return items;
  }

  document.addEventListener("contextmenu", (event) => {
    // The town's Streets view (docs/TownGrid.md 8): app.js builds the plot's
    // items (Go to, Go in, and the moon-coloured "Walk here now").
    const streets = event.target.closest?.("#settlementCanvas");
    if (streets && has("townCanvasMenu")) {
      const spec = window.townCanvasMenu(event);
      if (spec) {
        event.preventDefault();
        openMenuWith(spec, event.clientX, event.clientY, streets);
        return;
      }
    }
    const canvas = event.target.closest?.(MAP_CANVASES);
    if (canvas) {
      const t = tileAt(canvas, event);
      if (!t) return; // no map drawn yet: the browser menu is fine
      event.preventDefault();
      openMenuWith({ name: tileLabel(t), type: `tile · ${t.cx}, ${t.cy}`, items: mapActions(t) }, event.clientX, event.clientY, canvas);
      return;
    }
    const anchor = event.target.closest?.(MENU_ANCHORS);
    if (!anchor) return;
    const found = resolve(anchor);
    if (!found) return;
    event.preventDefault();
    // Shift+F10 and the Menu key arrive at (0,0); anchor the menu to the element.
    let x = event.clientX;
    let y = event.clientY;
    if (!x && !y) {
      const r = anchor.getBoundingClientRect();
      x = r.left + 8;
      y = r.bottom + 4;
    }
    openMenu(found, x, y, anchor);
  });
  document.addEventListener(
    "pointerdown",
    (event) => {
      if (menuOpen && !menuEl.contains(event.target)) closeMenu();
    },
    true
  );
  document.addEventListener("scroll", () => closeMenu(), true);
  window.addEventListener("resize", () => closeMenu());
  window.addEventListener("blur", () => closeMenu());

  /* ------------------------------------------------------------------------
     Re-apply after every render. app.js replaces innerHTML wholesale, so
     folds and provider filters are recomputed from the DOM, not patched.
     ------------------------------------------------------------------------ */

  let applyTimer = 0;
  function applyAll() {
    applyFolds();
    applyProviderFields();
  }
  const observer = new MutationObserver(() => {
    clearTimeout(applyTimer);
    applyTimer = setTimeout(applyAll, 60);
  });

  function boot() {
    applyAll();
    observer.observe(document.body, { childList: true, subtree: true });
    // The tour shows and hides by class; folds must follow it.
    const tour = document.querySelector("#setupTourLayer");
    if (tour) new MutationObserver(() => applyFolds()).observe(tour, { attributes: true, attributeFilter: ["class"] });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // A small public surface for the console and for tests.
  window.MorkynInteract = { applyFolds, applyProviderFields, resolve, tileAt, mapActions, closeMenu, hidePeek, openMenu: openMenuWith };
})();
