/* ==========================================================================
   Mørkyn UI · destination_marker.js  (the set destination on the maps)

   Status: built, not wired (TODO n22). This is the "destination is not drawn on the map" gap of that item.

   Draws state.travel_destination as a flag: on the lens and the Large map at the target world cell (or as a
   rim arrow when the cell is off the drawn window), on the Settlement canvas on the target city cell, and on
   the Streets canvas around the target plot (or the cell centre when the target is a cell). Reads only the
   canvas, the meta the painter stored on it (canvas._mapMeta / canvas._cityMeta) and the arguments it is
   given. The colour helper cssToken is read by bare name, guarded, wherever a painter needs a theme colour;
   settlementData, townData, townGeometry and townCellBox are read the same way only inside draw() for the
   two town modes. Nothing here fetches, stores or binds events, and nothing in the live page loads or calls
   this file.

   Wiring (not done):
     static/app.js:refreshLocalMap() -> after drawNpcMarkersOnCanvas(canvas, _lastNpcMarkers, data.player, "local"):
         window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, data.player, "local")
     static/app.js:refreshFullMap() -> after drawNpcMarkersOnCanvas(canvas, _lastNpcMarkers, data.player, "full"):
         window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, data.player, "full")
     static/app.js:paintSettlementCanvas() -> before the player ring (const you = city.player):
         window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, null, "settlement")
     static/app.js:paintTownCanvas() -> before the player ring (const you = townData.player):
         window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, null, "streets")
     static/app.js:repaintSettlementForSize() -> nothing more; it calls the two painters above
     static/app.js:renderMovePrompt() -> optional "shown on the map" note on the destination card
     static/index.html -> <script src="/static/ui/destination_marker.js?v=__BUNDLE__"> after app.js

   Turn on:
     [ ] the script line in static/index.html
     [ ] the four draw() lines above (each after the painter's own markers, before the next repaint)
     [ ] no server change, no route, no prompt

   Tests: tools/test_destination_marker.js (node)
   ========================================================================== */

(function () {
  "use strict";

  // The page's global object. In the browser this is window; the node test
  // sets global.window = {} before requiring the file. Nothing else is read
  // from it at load time.
  const root = typeof window !== "undefined" ? window : globalThis;

  /* ------------------------------------------------------------------------
     Rules (data). The numbers are the design's; tests pin them.
     ------------------------------------------------------------------------ */

  const STYLE = {
    // Colours resolve through cssToken(name, fallback) when app.js has it, else the fallback.
    fill: ["--thread-bright", "#ece4fb"],
    accent: ["--moon", "#d4566a"],
    ink: "rgba(0,0,0,0.85)",
    alpha: 0.95,
    poleFrac: 0.62, // flag pole height as a fraction of the cell
    pennantFrac: 0.34, // pennant width as a fraction of the cell
    minPx: 5, // the pole never shrinks below this in bitmap px
    rimBlipFrac: 8, // copies paintTileGrid: blip = max(6, round(8 * canvas.width / shownCssWidth))
    hereRingFrac: 0.42, // when the destination is the player's own cell: a ring, no flag
    streetsPad: 1.5, // CSS px outside a plot rect
    cellMarkTiles: 3, // Streets: a cell target marks a 3x3-tile square at the centre
  };

  const TARGET_KIND = (t) => (t?.plot ? "plot" : t?.city ? "city" : Number.isFinite(t?.x) && Number.isFinite(t?.y) ? "cell" : "");

  const WORLD_MODES = ["local", "full"];

  /* ------------------------------------------------------------------------
     Small helpers
     ------------------------------------------------------------------------ */

  // Only a finite number counts; null, "", booleans and arrays read as NaN so
  // targetCell agrees with TARGET_KIND (every coordinate reaches the page as a JSON number).
  const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : NaN);
  const isObj = (v) => v !== null && typeof v === "object";

  // A colour from the page's theme when app.js is loaded, else the fallback.
  function colour(entry) {
    if (!Array.isArray(entry)) return String(entry || "");
    const [name, fallback] = entry;
    try {
      if (typeof cssToken === "function") return cssToken(name, fallback) || fallback;
    } catch (_) {
      /* no page: fall through */
    }
    return fallback;
  }

  function mergeStyle(style) {
    return isObj(style) ? Object.assign({}, STYLE, style) : STYLE;
  }

  function report(drawn, reason) {
    return reason ? { drawn, reason } : { drawn };
  }

  function contextOf(canvas) {
    try {
      const ctx = canvas && typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
      return ctx || null;
    } catch (_) {
      return null;
    }
  }

  /* ------------------------------------------------------------------------
     Destination and target readers
     ------------------------------------------------------------------------ */

  function targetKind(target) {
    return TARGET_KIND(target);
  }

  function isSet(dest) {
    return Boolean(isObj(dest) && isObj(dest.target) && targetKind(dest.target));
  }

  function label(dest) {
    const text = isObj(dest) ? String(dest.label || "").trim() : "";
    return text || "Destination";
  }

  // "C7.1.0.12" -> [1, 0] (town_grid.plot_id is "<city>.<lx>.<ly>.<n>").
  function plotLocal(plotId) {
    const parts = String(plotId || "")
      .trim()
      .split(".");
    if (parts.length !== 4) return null;
    const lx = Number(parts[1]);
    const ly = Number(parts[2]);
    const n = Number(parts[3]);
    if (!Number.isInteger(lx) || !Number.isInteger(ly) || !Number.isInteger(n)) return null;
    if (parts[1] === "" || parts[2] === "" || parts[3] === "") return null;
    return [lx, ly];
  }

  // The world cell a target names, or null when it carries none.
  function targetCell(target) {
    if (!isObj(target)) return null;
    const x = num(target.x);
    const y = num(target.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x, y };
  }

  /* ------------------------------------------------------------------------
     Geometry (pure; no canvas needed)
     ------------------------------------------------------------------------ */

  // Pixel size of the drawn window, from the meta (width/height are tile
  // counts in canvas._mapMeta) or from an explicit {width, height} in px.
  function windowSize(meta, size) {
    if (isObj(size) && Number.isFinite(num(size.width)) && Number.isFinite(num(size.height))) {
      return { width: num(size.width), height: num(size.height) };
    }
    const cell = num(meta.cell);
    if (Number.isFinite(num(meta.width)) && Number.isFinite(num(meta.height))) {
      return { width: num(meta.width) * cell, height: num(meta.height) * cell };
    }
    if (Number.isFinite(num(meta.extent)) && num(meta.extent) > 0) {
      const tiles = 2 * num(meta.extent) + 1;
      return { width: tiles * cell, height: tiles * cell };
    }
    return null;
  }

  // Top-left bitmap px of the target's tile (the drawQuestMarkersOnCanvas formula).
  // `size` is optional: {width, height} of the canvas in px, used for the
  // on-screen test when known; else the meta's tile counts are used.
  function worldPoint(meta, target, playerPos, mode, size) {
    if (!isObj(meta) || !Number.isFinite(num(meta.cell)) || num(meta.cell) <= 0) return null;
    const cell = num(meta.cell);
    const at = targetCell(target);
    if (!at) return null;
    const local = (mode || meta.mode || "local") === "local";
    const relX = local ? at.x - (num(playerPos?.x) || 0) : at.x;
    const relY = local ? at.y - (num(playerPos?.y) || 0) : at.y;
    const px = (relX - (num(meta.minX) || 0)) * cell;
    const py = (relY - (num(meta.minY) || 0)) * cell;
    let inside = px >= 0 && py >= 0;
    const win = windowSize(meta, size);
    if (inside && win) inside = px < win.width && py < win.height;
    if (inside && meta.circle && win) {
      // The lens draws tiles inside a circle at the canvas centre; the player's
      // tile sits at the centre, so a tile's centre is relX * cell away from it.
      const circleR = Math.min(win.width, win.height) / 2 - 1;
      inside = Math.hypot(relX, relY) * cell <= circleR;
    }
    return { px, py, relX, relY, inside };
  }

  // The rim blip size paintTileGrid uses (the circle is CSS-scaled into a small slot).
  function rimBlip(canvas) {
    let shown = 0;
    try {
      shown = num(canvas.clientWidth) || (typeof canvas.getBoundingClientRect === "function" ? num(canvas.getBoundingClientRect().width) : 0) || 180;
    } catch (_) {
      shown = 180;
    }
    shown = Math.max(80, shown || 180);
    const pxScale = (num(canvas.width) || shown) / shown;
    return Math.max(6, Math.round(STYLE.rimBlipFrac * pxScale));
  }

  // A point on the lens rim in the direction of (relX, relY) from the centre.
  function rimPoint(canvas, meta, relX, relY) {
    const w = num(canvas?.width) || 0;
    const h = num(canvas?.height) || 0;
    const angle = Math.atan2(num(relY) || 0, num(relX) || 0);
    const cx = w / 2;
    const cy = h / 2;
    const circleR = Math.min(w, h) / 2 - 1;
    const blip = rimBlip(canvas || {});
    const rimR = Math.max(blip + 2, circleR - blip - 2);
    if (isObj(meta) && !meta.circle) {
      // The Large map is a rectangle: clamp the tile centre into the canvas edge.
      const cell = num(meta.cell) || 0;
      const tx = ((num(relX) || 0) - (num(meta.minX) || 0)) * cell + cell / 2;
      const ty = ((num(relY) || 0) - (num(meta.minY) || 0)) * cell + cell / 2;
      const pad = blip + 2;
      return {
        px: Math.min(Math.max(tx, pad), Math.max(pad, w - pad)),
        py: Math.min(Math.max(ty, pad), Math.max(pad, h - pad)),
        angle: Math.atan2(ty - cy, tx - cx),
      };
    }
    return { px: cx + Math.cos(angle) * rimR, py: cy + Math.sin(angle) * rimR, angle };
  }

  // The settlement cell a target lands on, by world (x, y) first, then by the plot id's [lx, ly].
  function settlementCell(cells, target) {
    const list = Array.isArray(cells) ? cells.filter(isObj) : [];
    const at = targetCell(target);
    if (at) {
      const byXy = list.find((c) => num(c.x) === at.x && num(c.y) === at.y);
      if (byXy) return byXy;
    }
    const local = target?.plot ? plotLocal(target.plot) : null;
    if (local) {
      const byLocal = list.find((c) => Array.isArray(c.local) && num(c.local[0]) === local[0] && num(c.local[1]) === local[1]);
      if (byLocal) return byLocal;
    }
    return null;
  }

  // Centre of the target's cell on the Settlement canvas, in bitmap px.
  function cityPoint(cityMeta, settlement, target) {
    if (!isObj(cityMeta) || !isObj(settlement) || !isObj(target)) return null;
    const unit = num(cityMeta.unit);
    if (!Number.isFinite(unit) || unit <= 0) return null;
    const shown = String(settlement.id || "");
    const wanted = String(target.city || "");
    if (!shown || !wanted || shown !== wanted) return null;
    const cells = Array.isArray(cityMeta.cells) && cityMeta.cells.length ? cityMeta.cells : settlement.cells;
    const cell = settlementCell(cells, target);
    if (!cell) return null;
    const lx = num(Array.isArray(cell.local) ? cell.local[0] : NaN) || 0;
    const ly = num(Array.isArray(cell.local) ? cell.local[1] : NaN) || 0;
    const ox = num(cityMeta.ox) || 0;
    const oy = num(cityMeta.oy) || 0;
    return {
      px: ox + lx * unit + unit / 2,
      py: oy + ly * unit + unit / 2,
      cellX: num(cell.x),
      cellY: num(cell.y),
      unit,
    };
  }

  // The Streets cell a target lands on: by (cx, cy), else the cell holding the plot id.
  function streetsCell(cells, target) {
    const list = Array.isArray(cells) ? cells.filter(isObj) : [];
    const at = targetCell(target);
    if (at) {
      const byXy = list.find((c) => num(c.cx) === at.x && num(c.cy) === at.y);
      if (byXy) return byXy;
    }
    if (target?.plot) {
      const pid = String(target.plot);
      const byPlot = list.find((c) => Array.isArray(c.plots) && c.plots.some((p) => isObj(p) && String(p.id) === pid));
      if (byPlot) return byPlot;
    }
    return null;
  }

  // A box in CSS px around the target plot, or a 3x3-tile square at the cell centre.
  function streetsBox(geo, townData, target, cellBoxFn) {
    if (!isObj(geo) || !isObj(townData) || !isObj(target) || typeof cellBoxFn !== "function") return null;
    const shown = String(townData.city_id || "");
    const wanted = String(target.city || "");
    if (shown && wanted && shown !== wanted) return null;
    const cell = streetsCell(townData.cells, target);
    if (!cell) return null;
    let box;
    try {
      box = cellBoxFn(geo, cell);
    } catch (_) {
      box = null;
    }
    if (!isObj(box) || !Number.isFinite(num(box.tile)) || num(box.tile) <= 0) return null;
    const tile = num(box.tile);
    const x0 = num(box.x0) || 0;
    const y0 = num(box.y0) || 0;
    if (target.plot) {
      const pid = String(target.plot);
      const plot = (Array.isArray(cell.plots) ? cell.plots : []).find((p) => isObj(p) && String(p.id) === pid);
      const r = plot && Array.isArray(plot.r) && plot.r.length === 4 ? plot.r.map(num) : null;
      if (r && r.every(Number.isFinite)) {
        return { x0: x0 + r[0] * tile, y0: y0 + r[1] * tile, w: r[2] * tile, h: r[3] * tile, tile, kind: "plot" };
      }
    }
    const side = Math.max(1, num(cell.side) || 1);
    const cellPx = Number.isFinite(num(geo.cellPx)) && num(geo.cellPx) > 0 ? num(geo.cellPx) : side * tile;
    const half = (STYLE.cellMarkTiles * tile) / 2;
    return {
      x0: x0 + cellPx / 2 - half,
      y0: y0 + cellPx / 2 - half,
      w: STYLE.cellMarkTiles * tile,
      h: STYLE.cellMarkTiles * tile,
      tile,
      kind: "cell",
    };
  }

  /* ------------------------------------------------------------------------
     Painters (each wraps the context in save/restore)
     ------------------------------------------------------------------------ */

  // A flag on the tile whose top-left is (px, py): a pole and a pennant.
  function paintFlag(ctx, px, py, cell, style) {
    if (!ctx) return;
    const s = mergeStyle(style);
    const size = Math.max(1, num(cell) || 1);
    const pole = Math.max(s.minPx, size * s.poleFrac);
    const pennant = Math.max(3, size * s.pennantFrac);
    const baseX = px + size * 0.36;
    const baseY = py + size - Math.max(1, size * 0.08);
    const topY = baseY - pole;
    try {
      ctx.save();
      ctx.globalAlpha = s.alpha;
      ctx.lineCap = "round";
      // Pole
      ctx.beginPath();
      ctx.moveTo(baseX, baseY);
      ctx.lineTo(baseX, topY);
      ctx.strokeStyle = s.ink;
      ctx.lineWidth = Math.max(2.5, size / 8);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(baseX, baseY);
      ctx.lineTo(baseX, topY);
      ctx.strokeStyle = colour(s.fill);
      ctx.lineWidth = Math.max(1, size / 16);
      ctx.stroke();
      // Pennant
      ctx.beginPath();
      ctx.moveTo(baseX, topY);
      ctx.lineTo(baseX + pennant, topY + pennant * 0.42);
      ctx.lineTo(baseX, topY + pennant * 0.84);
      ctx.closePath();
      ctx.fillStyle = colour(s.accent);
      ctx.fill();
      ctx.strokeStyle = s.ink;
      ctx.lineWidth = Math.max(1, size / 20);
      ctx.stroke();
      // Foot
      ctx.beginPath();
      ctx.arc(baseX, baseY, Math.max(1.5, size / 12), 0, Math.PI * 2);
      ctx.fillStyle = colour(s.fill);
      ctx.fill();
    } catch (_) {
      /* a context without a method: leave the painter's state alone */
    } finally {
      try {
        ctx.restore();
      } catch (_) {
        /* ignore */
      }
    }
  }

  // A small arrow on the rim at (px, py), pointing along `angle` (radians).
  function paintRimArrow(ctx, px, py, angle, size, style) {
    if (!ctx) return;
    const s = mergeStyle(style);
    const r = Math.max(4, num(size) || 6);
    const a = num(angle) || 0;
    const tip = [px + Math.cos(a) * r, py + Math.sin(a) * r];
    const left = [px + Math.cos(a + (Math.PI * 2) / 3) * r, py + Math.sin(a + (Math.PI * 2) / 3) * r];
    const right = [px + Math.cos(a - (Math.PI * 2) / 3) * r, py + Math.sin(a - (Math.PI * 2) / 3) * r];
    try {
      ctx.save();
      ctx.globalAlpha = s.alpha;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(tip[0], tip[1]);
      ctx.lineTo(left[0], left[1]);
      ctx.lineTo(right[0], right[1]);
      ctx.closePath();
      ctx.fillStyle = colour(s.accent);
      ctx.fill();
      ctx.strokeStyle = s.ink;
      ctx.lineWidth = Math.max(1, r / 5);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(px, py, Math.max(1.5, r / 4), 0, Math.PI * 2);
      ctx.fillStyle = colour(s.fill);
      ctx.fill();
    } catch (_) {
      /* ignore */
    } finally {
      try {
        ctx.restore();
      } catch (_) {
        /* ignore */
      }
    }
  }

  // A ring on the tile whose top-left is (px, py): the destination is here.
  function paintHereRing(ctx, px, py, cell, style) {
    if (!ctx) return;
    const s = mergeStyle(style);
    const size = Math.max(1, num(cell) || 1);
    const cx = px + size / 2;
    const cy = py + size / 2;
    const r = Math.max(3, size * s.hereRingFrac);
    try {
      ctx.save();
      ctx.globalAlpha = s.alpha;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = s.ink;
      ctx.lineWidth = Math.max(3, size / 7);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = colour(s.accent);
      ctx.lineWidth = Math.max(1.5, size / 14);
      ctx.stroke();
    } catch (_) {
      /* ignore */
    } finally {
      try {
        ctx.restore();
      } catch (_) {
        /* ignore */
      }
    }
  }

  // A box (CSS px, Streets canvas) padded by streetsPad; a plot gets a corner flag too.
  function paintBox(ctx, box, style) {
    if (!ctx || !isObj(box)) return;
    const s = mergeStyle(style);
    const pad = num(s.streetsPad) || 0;
    const x0 = (num(box.x0) || 0) - pad;
    const y0 = (num(box.y0) || 0) - pad;
    const w = Math.max(1, (num(box.w) || 0) + pad * 2);
    const h = Math.max(1, (num(box.h) || 0) + pad * 2);
    try {
      ctx.save();
      ctx.globalAlpha = s.alpha;
      ctx.lineJoin = "round";
      ctx.strokeStyle = s.ink;
      ctx.lineWidth = 3.5;
      ctx.strokeRect(x0, y0, w, h);
      ctx.strokeStyle = colour(s.accent);
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x0, y0, w, h);
      if (box.kind === "plot") {
        const tile = Math.max(2, num(box.tile) || 2);
        paintFlag(ctx, x0 + w - tile * 1.5, y0 - tile * 1.2, tile * 1.5, s);
      }
    } catch (_) {
      /* ignore */
    } finally {
      try {
        ctx.restore();
      } catch (_) {
        /* ignore */
      }
    }
  }

  /* ------------------------------------------------------------------------
     Draw entry points (one per view)
     ------------------------------------------------------------------------ */

  // Lens ("local") and Large map ("full"): a flag on the cell, a rim arrow off-window, a ring when here.
  function drawWorld(canvas, dest, playerPos, mode) {
    if (!isSet(dest)) return report("none", "no_destination");
    if (!WORLD_MODES.includes(mode)) return report("none", "wrong_mode");
    if (!isObj(canvas) || !isObj(canvas._mapMeta)) return report("none", "no_meta");
    const meta = canvas._mapMeta;
    const at = targetCell(dest.target);
    if (!at) return report("none", "unknown_cell");
    const point = worldPoint(meta, dest.target, playerPos, mode, { width: num(canvas.width), height: num(canvas.height) });
    if (!point) return report("none", "no_meta");
    const ctx = contextOf(canvas);
    if (!ctx) return report("none", "no_ctx");
    const cell = num(meta.cell);
    const here = isObj(playerPos) && num(playerPos.x) === at.x && num(playerPos.y) === at.y;
    if (here && point.inside) {
      paintHereRing(ctx, point.px, point.py, cell);
      return report("here");
    }
    if (point.inside) {
      paintFlag(ctx, point.px, point.py, cell);
      return report("pin");
    }
    const rim = rimPoint(canvas, meta, point.relX, point.relY);
    paintRimArrow(ctx, rim.px, rim.py, rim.angle, rimBlip(canvas));
    return report("rim");
  }

  // Settlement (city) canvas: a flag on the target's city cell.
  function drawSettlement(canvas, dest, settlementData) {
    if (!isSet(dest)) return report("none", "no_destination");
    if (!isObj(canvas) || !isObj(canvas._cityMeta)) return report("none", "no_meta");
    const city = isObj(settlementData) ? settlementData.settlement : null;
    if (!isObj(city)) return report("none", "no_meta");
    const point = cityPoint(canvas._cityMeta, city, dest.target);
    if (!point) return report("none", "off_city");
    const ctx = contextOf(canvas);
    if (!ctx) return report("none", "no_ctx");
    const you = isObj(city.player) ? city.player : null;
    const here = you && num(you.x) === point.cellX && num(you.y) === point.cellY;
    const px = point.px - point.unit / 2;
    const py = point.py - point.unit / 2;
    if (here) {
      paintHereRing(ctx, px, py, point.unit);
      return report("here");
    }
    paintFlag(ctx, px, py, point.unit);
    return report("pin");
  }

  // Streets canvas: a box around the target plot, or a square at the cell centre.
  function drawStreets(canvas, dest, townData, geo, cellBoxFn) {
    if (!isSet(dest)) return report("none", "no_destination");
    if (!isObj(canvas) || !isObj(townData) || !Array.isArray(townData.cells) || !isObj(geo) || typeof cellBoxFn !== "function") {
      return report("none", "no_meta");
    }
    const box = streetsBox(geo, townData, dest.target, cellBoxFn);
    if (!box) return report("none", "unknown_cell");
    const ctx = contextOf(canvas);
    if (!ctx) return report("none", "no_ctx");
    const you = isObj(townData.player) ? townData.player : null;
    const cell = streetsCell(townData.cells, dest.target);
    const sameCell = Boolean(you && cell && num(you.cx) === num(cell.cx) && num(you.cy) === num(cell.cy));
    let here = false;
    if (sameCell && box.kind === "cell") here = true;
    if (sameCell && box.kind === "plot" && String(you.plot || "") === String(dest.target.plot)) here = true;
    if (here) {
      const side = Math.max(1, num(cell.side) || 1);
      const cellPx = Number.isFinite(num(geo.cellPx)) && num(geo.cellPx) > 0 ? num(geo.cellPx) : side * box.tile;
      const ring = Math.max(box.tile * STYLE.cellMarkTiles, 6);
      const cx = box.x0 + box.w / 2;
      const cy = box.y0 + box.h / 2;
      paintHereRing(ctx, cx - ring / 2, cy - ring / 2, Math.min(ring, cellPx));
      return report("here");
    }
    paintBox(ctx, box);
    return report("pin");
  }

  // Dispatcher: the one call a repaint path would make. The two town modes read
  // the painter's globals by bare name, guarded; missing ones mean "no_meta".
  function draw(canvas, dest, playerPos, mode) {
    if (mode === "local" || mode === "full") return drawWorld(canvas, dest, playerPos, mode);
    if (mode === "settlement") {
      const data = typeof settlementData !== "undefined" ? settlementData : undefined;
      if (!isObj(data)) return isSet(dest) ? report("none", "no_meta") : report("none", "no_destination");
      return drawSettlement(canvas, dest, data);
    }
    if (mode === "streets") {
      const town = typeof townData !== "undefined" ? townData : undefined;
      const geoFn = typeof townGeometry === "function" ? townGeometry : null;
      const boxFn = typeof townCellBox === "function" ? townCellBox : null;
      if (!isObj(town) || !geoFn || !boxFn) return isSet(dest) ? report("none", "no_meta") : report("none", "no_destination");
      let geo = null;
      try {
        geo = geoFn(canvas);
      } catch (_) {
        geo = null;
      }
      if (!isObj(geo)) return isSet(dest) ? report("none", "no_meta") : report("none", "no_destination");
      return drawStreets(canvas, dest, town, geo, boxFn);
    }
    return isSet(dest) ? report("none", "wrong_mode") : report("none", "no_destination");
  }

  root.MorkynDestinationMarker = {
    isSet,
    label,
    targetKind,
    plotLocal,
    worldPoint,
    rimPoint,
    cityPoint,
    streetsBox,
    paintFlag,
    paintRimArrow,
    paintHereRing,
    paintBox,
    drawWorld,
    drawSettlement,
    drawStreets,
    draw,
    STYLE,
    TARGET_KIND,
  };
})();
