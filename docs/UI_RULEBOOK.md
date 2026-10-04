# UI Rulebook

How the Mørkyn interface is built, how to change it without breaking it, and what
"looks right" means here. Read this before touching anything under `static/`.

The short version: **values live in `tokens.css`, layout lives in `styles.css`,
looks live in `skin.css`, and `app.js` owns every id and class name.** If you
can say which of those four sentences your change belongs to, you know which
file to open.

---

## 1. The four parts

| File | Layer | Owns | Never contains |
| --- | --- | --- | --- |
| `static/ui/tokens.css` | 1 · values | every colour, font stack, radius, shadow, spacing step; the five themes | selectors other than `:root` and `html[data-theme=…]` |
| `static/styles.css` | 2 · layout engine | `display`, grid/flex, sizes, positions, `overflow`, responsive rules, show/hide states | a literal colour, font, radius, or shadow (reference a token instead) |
| `static/ui/skin.css` | 3 · look | colour, border, background, shadow, font, letter-spacing, text-transform, masks, per-component dress | anything that moves an element: `display`, `grid-*`, `flex`, `width`, `height`, `margin`, `padding`, `position` |
| `static/app.js` | behaviour | every `id`, every class it queries or toggles, canvas paint | — (but see §7 for what it must ask the tokens for) |
| `static/ui/interact.js` | interaction | folds, hover peeks, right-click menus, provider-aware forms; everything is delegated and re-applied after app.js re-renders | any rendering of game content; it only reads what app.js drew |

They load in that order from `index.html` and `popout.html`. Because `skin.css`
is last, a rule in it with the same specificity beats the same selector in
`styles.css`. That is the whole mechanism: the engine lays things out, the skin
dresses them, and nothing has to be deleted from the engine to restyle it.

`app/main.py` lists the three stylesheets and `ui/interact.js` in
`BUNDLE_ASSETS`, so the cache-busting token changes whenever any of them
changes. Add a fourth file
and you must add it there too, or returning browsers will never fetch it.
`tests/test_asset_cache_token.py` checks that the files listed there are the
files `index.html` links.

---

## 2. Where does my change go?

| I want to… | Open | Section |
| --- | --- | --- |
| shift the colour of the whole UI | `tokens.css` | `--thread-h` and `--thread-s` in `:root` |
| make one theme moodier | `tokens.css` | its `html[data-theme=…]` block |
| add a theme | `tokens.css` + `app.js` + `index.html` | §6 |
| change how all buttons look | `skin.css` | 05 Controls |
| make one button look different | `skin.css` | the screen's section (06–12), by id |
| change a heading's typeface, size, or tracking | `skin.css` | 04 Type |
| give a container cut corners (make it a shard) | `skin.css` | 02 Shards (add the selector to the list) |
| put a needle or a fading line on something | `skin.css` | 03 Threads |
| move something, resize it, change wrapping | `styles.css` | search for the selector |
| hide or show something in a state | `styles.css` | the state class rules (`.sceneFocus`, `.customLayout`, `body.play-menu-open`, …) |
| a new element the JS creates | `styles.css` for layout, `skin.css` for look; name it in `app.js` once | — |
| colour drawn on a canvas | `app.js`, via `cssToken("--name", fallback)` | §7 |
| make a section collapsible | `interact.js` | add its heading selector to `FOLD_HEADINGS` (§3.7) |
| give a thing a hover peek or a right-click menu | `interact.js` | `PEEK_ANCHORS` / `MENU_ANCHORS` and `buildActions` (§3.7) |
| show a settings field only for one provider | `interact.js` | `PROVIDER_FORMS` (§3.7) |

If a change needs both a layout and a look edit, make both; do not put a colour
into `styles.css` because you were already there.

---

## 3. The look

The interface is derived from the logo and key art in `Media/`: a black void,
a vertical spire, and thin filaments of violet-white light crossing it. Three
ideas follow from that, and every rule in `skin.css` is one of them.

### 3.1 One light, called the thread

There is one luminous colour. It is a hue and a saturation (`--thread-h`,
`--thread-s`), and every bright token is built from those two numbers:
`--thread`, `--thread-bright`, `--thread-deep`, `--thread-dim`,
`--thread-soft`, `--thread-ghost`, and the halo `--thread-halo`. The void
(`--bg`, `--ink`, the `--surface-*` steps) carries a faint cast of the same hue,
so the page and its light always agree.

**Light is always a line.** The thread appears as one-pixel borders, hairline
rules, needles, the ring around the map, the drop cap, and text. It is never a
filled block. The primary button is a shard outlined in thread with a faint
halo and a near-transparent fill, not a solid coloured slab. This is the single
rule that keeps Mørkyn from looking like every other dark RPG, which all fill
their buttons with gold or green.

The red moon is the only second colour (`--moon`), and it is a signal: damage,
errors, danger. `--warn` and `--good` exist for rewards and success and are
used sparingly. Nothing else is coloured.

### 3.2 Shards, not boxes

The art is broken black slabs with sharp edges, so containers have no radius
anywhere, and the important ones have two opposite corners cut at 45°. That
cut container is a **shard**. It is drawn entirely with background gradients
(two corner squares holding a diagonal, four edge strips, three fill
rectangles), so it needs no extra markup and no clip-path, and it is tuned per
element with three tokens:

| Token | Meaning | Default |
| --- | --- | --- |
| `--shard-cut` | size of the cut corner | 10px (7px on buttons, 14–16px on panels) |
| `--shard-fill` | the slab colour | `--surface-solid` |
| `--shard-line` | the one-pixel thread around it | `--thread-dim` |

Who is a shard: the main menu panel, modals, the setup panel, the scene box,
the drawers, floating tab windows, the busy and splash cards, and every
primary button. The list is one selector group in `skin.css` 02; to make
something a shard, add it there and set its tokens in its own section.

Who is not: anything inside a list or a form. Cards (quests, history items,
setting groups, the Move and You cards under the map) are plain slabs with one
hairline and no cut.

### 3.3 Threads and needles

A **thread** is a one-pixel line of light that fades out. Panel headers end in
one that fades to the right (`border-image` with a gradient). Column seams
fade downward. The top bar's bottom edge is the brightest thread on the play
screen. Three faint threads cross the whole page behind everything
(`body::before`), like the filaments in the art.

A **needle** is a short vertical thread used as a marker: the drag grip on
panel headers, the left edge of a pressed drawer row or active tab category,
and the bar beside a section heading. It is always a gradient that fades at
both ends, never a solid bar.

### 3.4 Type

| Token | Stack | Use for |
| --- | --- | --- |
| `--font` | Segoe UI / Inter / system sans | nearly everything: titles, controls, labels, help |
| `--font-display` | Bodoni MT / Didot / high-contrast serif | the wordmark in the top bar and the narration drop cap, nothing else |
| `--font-narration` | Georgia / Palatino | narration, the player's last input, the composer, taglines |

- **Wordmark** `Mørkyn`: display, mixed case, `--track-title`, thread-bright.
  On the main menu the title is the logo image itself, cropped and faded with
  a mask; the text stays in the DOM for assistive tech.
- **Title** (`h1`, modal and drawer `h2`): sans, weight 300, lightly tracked.
- **Eyebrow** (`SCENE`, `MAP`, `OPTIONAL`, group labels): sans, 0.66rem,
  weight 600, uppercase, `--track-label`, colour `--label`. Every small tracked
  label is this one style; the selector list is in `skin.css` 04.
- **Narration**: narration stack, 1.02rem, line-height 1.72, drop cap in the
  display face coloured thread.
- Nothing has a text-shadow. Nothing has gradient-filled text. No serif
  uppercase anywhere: that is the generic-fantasy tell.

### 3.5 Controls

| Tier | Selector(s) | Look |
| --- | --- | --- |
| **Primary** | `#sendButton`, `#setupStart`, `.mainMenuPrimary`, `button.primary`, `.primaryButton` | shard, thread outline, faint halo, thread-bright uppercase text |
| **Button** | `button`, `.buttonLike`, `.secondaryButton`, `.mainMenuSecondary` | slab, hairline, sans sentence case; thread text on hover |
| **Chip** | `.chipBtn`, d-pad, `.playMenuToggle`, index tabs, Ask/Help | small, tracked uppercase sans; active = thread-soft fill, thread outline |

Buttons that carry a *label* ("Map", "Send", "North") may be uppercase; buttons
that carry a *name* (an NPC, an item, a save slot, which app.js renders by the
hundred) must not, so the default button stays sentence case.

Fields are wells in the void (`--surface-inset`, inset shadow), hairline
border, thread border and halo on focus, italic placeholders. Checkboxes and
radios are 16px and take `accent-color` from the thread.

### 3.6 Shapes by tier

Every control's silhouette says what it is:

| Shape | Who | How |
| --- | --- | --- |
| two cuts (top-left and bottom-right) | whole-task containers and the one primary action | `--shard-cut` |
| one cut (bottom-right only) | chips, index tabs, d-pad, Details/Link buttons, preset chips | `--shard-cut-tl: 0` |
| rectangle | ordinary buttons, fields, cards | no shard |

The cut is drawn by the shard mixin in `skin.css` 02, so a chip is in the same
selector list as a panel; it just sets `--shard-cut-tl` to zero.

### 3.7 Interaction: folds, peeks, menus

The screens are dense on purpose, and three behaviours in `interact.js` keep
them usable without adding chrome:

- **Folds.** Any heading matching `FOLD_HEADINGS` (section subheads, the
  Move/You/Present card titles, character-sheet and save-editor headings, the
  setup Primary/Optional heads) becomes a toggle with a small chevron. Folding
  hides the siblings up to the next heading. The choice is stored per screen
  and heading in `localStorage` and re-applied after every re-render through
  a `MutationObserver`, so app.js never needs to know. A heading with
  `data-fold-default="closed"` starts folded until the player opens it once
  (the six optional setup sections and the map-art tools do this). Nothing
  is folded while the first-run tour is showing.
- **Peeks.** Hovering an NPC, item, place, event, skill, or ability (an
  `.entityLink`, a dock card, a pack chip, a bible card) shows a translucent
  shard with the short version after 220 ms. It never takes the pointer, it
  hides on scroll and on click, and it does not fire on touch. Items reuse
  app.js's own `itemOverlayHtml`, so inventory rows and pack chips agree.
  Peeks are for things with a one-paragraph summary; a form or a quest log
  gets a fold, not a peek.
- **Right-click.** The same anchors open a context menu. Every action that
  the game would treat as a turn (talk, ask, examine, equip, use, drop, go
  to) only writes the sentence into *What will you do?* and leaves Send to
  the player. Actions that act immediately say so in their label ("Attack …
  now") and are coloured with the red moon. Shift+F10 and long-press open
  the same menu; arrows move, Escape closes.
- **Right-click on the map.** Both canvases (the lens beside the scene and
  the world overlay) open a tile menu: step or travel there (with the same
  long-travel gate as a click), who is here, about a settlement or known
  place, write "go to …" into the input, open the world map, copy the
  coordinates. The tile is found exactly as app.js's own click handlers find
  it, from `canvas._mapMeta` and the view object, so the two never disagree.
- **Provider-aware forms.** The LLM settings and app settings forms show only
  the fields that belong to the selected provider; the rest get
  `.uiOffProvider`. The values are still in the form and still save.
- **Failsafes** (`static/ui/failsafe.js`, `app/failsafe.py`). A model failure
  never arrives as a bare exception string. The server classifies it into a
  problem (code, title, summary, tips, optional fallback) and the browser
  shows one dialog for all of them: the tips, "Retry", "Open LLM settings",
  and, when there is a fallback, a primary "Continue anyway" that says what
  it will do (the offline narrator for a turn; the 8192-token context when
  the requested size did not fit). The turn is only written after the player
  chooses; nothing falls back silently. New failure kinds get a rule and a
  copy block in `app/failsafe.py` first, then the mirror in `failsafe.js`.

What this means for new UI: when app.js renders a new kind of thing with a
name, give it `data-code` (or a `[[CODE]]` in `data-link-token`) and it gets
peeks and menus for free. When it renders a new section, give the heading one
of the fold classes. Do not add a second tooltip or a second menu system.

### 3.8 Depth and motion

Depth is almost entirely the hairlines. Shards that float (modals, the main
menu, popovers) get `--shadow-soft`, which is blurred wide enough that the cut
corners do not reveal a square. Nothing else has a shadow. No
`backdrop-filter`. The only glow is `--thread-halo`, and it is only ever
attached to a one-pixel thread (primary buttons, focused fields, the map ring),
never to a fill.

Transitions are what `styles.css` already has. `skin.css` adds none and ends
with a `prefers-reduced-motion` guard.

---

## 4. Rules

1. **A value appears once.** If you type a hex colour, an `hsl()`, a font
   name, a pixel radius, or a shadow anywhere but `tokens.css`, stop and make a
   token or use one. The only exceptions are `0`, `1px` hairlines,
   `transparent`, and the `#000` inside a mask.
2. **Light is a line.** No token from the thread family goes into a
   `background` as a solid fill larger than a hairline. `--thread-soft` and
   `--thread-ghost` are the only fills, and they are near-transparent.
3. **Layout and look do not share a file.** `skin.css` does not move things;
   `styles.css` does not dress them. When you find yourself writing `display:`
   in the skin or `color:` in the engine, you are in the wrong file.
4. **Match specificity, do not escalate it.** To override a rule, copy its
   selector into `skin.css`. Do not add an id to win. Do not add `!important`.
   The engine already uses `!important` in a few legacy spots (`.chipBtn`,
   `.activeChip`, `.tabCategoryBtn`, `.mapMainCanvas`, `.chatThinkingElapsed`,
   `.hidden`, `[hidden]`); when you must override one of those, you may match
   it, and you must leave a comment saying which rule you are matching.
5. **Ids and classes are an API.** `app.js` finds elements by id and toggles
   classes by name. Before renaming or removing either, run
   `grep -n "theName" static/app.js`. If it is there, it stays.
6. **New JS-created elements get one class, named in app.js, styled in CSS.**
   No inline `style=` from JS except for values that are genuinely runtime
   (a float window's `--float-w`, a progress width).
7. **A theme is two numbers.** A theme block sets `--thread-h` and
   `--thread-s` and, only if the hue must be removed from the void as well
   (ash), the surface tokens. It never changes a font, a radius, or a layout.
8. **Keep the lists as lists.** The shard list (02), the eyebrow list (04), and
   the primary list (05) are each one selector group. When something new needs
   that treatment, add its selector there. Do not copy the declarations.
9. **The `hidden` attribute wins.** `styles.css` sets `[hidden] { display: none
   !important }` on purpose. Do not write a rule that makes a `[hidden]`
   element visible.
10. **Files keep their own line endings.** `styles.css` is CRLF; `index.html`,
    `app.js`, and the `ui/` files are LF. Edit with a tool that preserves
    endings; a mixed file shows up as a whole-file diff.
11. **Look at it.** Every change to these files is followed by §8. A rule you
    did not see rendered is a rule you did not test.

---

## 5. Token reference

Everything in `:root` of `tokens.css`, by group.

**The thread:** `--thread-h`, `--thread-s`, and from them `--thread`,
`--thread-bright`, `--thread-deep`, `--thread-dim`, `--thread-soft`,
`--thread-ghost`, `--thread-halo`.

**Type:** `--font`, `--font-display`, `--font-narration`, `--font-mono`,
`--track-label` (0.18em), `--track-title` (0.08em).

**The void:** `--bg`, `--ink`, `--surface`, `--surface-solid`, `--surface-2`,
`--surface-3`, `--surface-inset`, `--bg-glow`, `--bg-glow-2`.
Aliases kept for old rules: `--panel`, `--surface-1`, `--card-bg-2`.

**Lines and text:** `--line`, `--line-strong`, `--line-etched`, `--text`,
`--muted`, `--muted-2`, `--label`, `--label-dim`. Aliases: `--border`,
`--text-muted`.

**Accents:** `--accent`, `--accent-soft`, `--accent-strong`, `--accent-deep`
(all aliases of the thread), `--accent-2`, `--accent-2-soft` (a grey of the
hue), `--moon`, `--moon-soft`, `--warn`, `--bad`, `--good`, `--on-accent`.
Legacy aliases: `--neon`, `--neon-1`, `--neon-dim`, `--neon-2`,
`--neon-2-dim`, `--neon-edge`, `--neon-glow` and `--scene-glow` (zero-size
transparent shadows, because a shadow list cannot contain `none`).

**Shards:** `--shard-cut`, `--shard-cut-tl`, `--shard-cut-br` (default to
`--shard-cut`; a chip sets `--shard-cut-tl: 0`), `--shard-fill`,
`--shard-line`.

**Controls:** `--btn-bg`, `--btn-bg-hover`, `--btn-border`, `--btn-text`,
`--field-bg`.

**Shape and depth:** `--radius-xs` … `--radius-lg`, `--radius-pill` (all 0;
kept so old rules resolve), `--shadow-soft`, `--shadow-sm`, `--bevel`,
`--inset`, `--decal-opacity`.

**Spacing:** `--space-1` (4px) … `--space-6` (32px). New layout rules in
`styles.css` should use these; old ones use literal pixels and may be
converted as they are touched.

**Layout:** `--play-menu-width`.

---

## 6. Themes

Five themes, one structure: the thread changes hue and the void follows it.
`dusk` (default) is violet, the logo's own light. `ember` is the red moon from
the key art. `tide` is a cold cyan filament. `bloom` is magenta. `ash` is a
white thread on a neutral black, the one theme that also overrides the surface
tokens so the void loses its cast.

A theme is an attribute on `<html>`: `data-theme="ember"`. No attribute means
dusk. `app.js` sets it (`applyTheme`, beside the `THEME_DEFAULT` constant) from
the setup page's theme select and the saved preference.

To add a theme, in this order:

1. `tokens.css`: add an `html[data-theme="name"]` block with `--thread-h` and
   `--thread-s`. Keep the comment line that names the mood.
2. `app.js`: add the name to the `allowed` set in `applyTheme`.
3. `index.html`: add an `<option>` to the setup theme select (search for the
   existing option text "Dusk").
4. Run §8 with `--themes` and look at the main menu in the new theme.

---

## 7. What app.js must ask the tokens for

Canvas paint does not see the CSS cascade. Anything drawn with `fillStyle` or
`strokeStyle` that should follow the theme reads a token through
`cssToken("--name", fallback)` (defined beside `applyTheme`). The empty map
well already does this with `--ink`. Map *tile* colours (grass, water, stone)
are world art, not interface, and stay hardcoded in the map drawing code.

Everything else app.js does to appearance is adding or removing a class. If
you find it setting `el.style.color` or `el.style.background`, move that to a
class and a rule.

The main menu loads `Media/morkyn-key-art.png` and `Media/morkyn-logo.png`
through the `/media` mount in `app/main.py`. If those files move, the two
`url()`s in `skin.css` 06 move with them.

---

## 8. Check your work

Start a server that is **not** using your real save, then capture every
surface:

```powershell
$env:AI_RPG_DB = "$env:TEMP\morkyn-shots.db"
$env:AI_RPG_CAMPAIGN_SLOTS = "$env:TEMP\morkyn-shots-slots"
.venv\Scripts\python -m uvicorn app.main:app --port 8765
# in another terminal:
python tools\capture_skin_shots.py --themes --import-debug-save
```

Both environment variables matter: the import that fills the play view
replaces whatever world the server is holding, and autosave writes into the
slot folder. Pointed at temp paths, neither can reach `data/`.

The script writes to `data/ui-shots/` (gitignored): the main menu in all five
themes, the setup page, the model settings modal, and the play view with the
drawer, the Tools tab, and scene focus, at 1440×960 and 1280×800. Open them
next to `Media/morkyn-key-art.png`. Then check, in order:

- [ ] It looks like it shipped with the key art. If the art and the UI could be
      from two different products, something is filled that should be a line.
- [ ] One primary per screen, outlined not filled, and it is the action you
      would press first.
- [ ] Every shard shows both cut corners. A shard with a square corner has a
      `border` or `border-radius` leaking in from the engine.
- [ ] Every small tracked label is the eyebrow style. No serif uppercase.
- [ ] No glow on a fill, no blur, no radius. Nothing coloured that is not the
      thread or a signal.
- [ ] 1280×800: nothing clipped at the bottom of the map column or the drawer.
- [ ] All five themes: the primary button and the wordmark are legible; the
      map ring is visible against the well.
- [ ] `python -m unittest tests.test_asset_cache_token` passes, so the page
      links what the bundle hashes.

If you changed `styles.css`, also open the pop-out (`/static/popout.html`)
and the save browser, which share it.

---

## 9. Known debt

Things the engine still does that this rulebook says not to. Fix them as the
rules around them are touched; do not fix them all at once.

- `styles.css` references `--neon*` in ~300 places and uses literal pixel
  spacing throughout. Both work through the aliases and need no action, but a
  rule being edited should be converted to the real token and the spacing scale.
- `styles.css` carries 146 `!important`s. Most guard show/hide states and are
  fine; the ones on `.chipBtn`, `.activeChip`, and `.tabCategoryBtn` force the
  skin to match them (rule 4).
- A few rarity and status colours (`.rarity-unique`, the watch-pin violet) are
  literals in `styles.css`. They are signal colours and should become tokens.
- `index.html` keeps an inline `<style>` for the script-blocked gate so that
  screen renders without any external CSS. Its colours are intentionally
  hardcoded; keep them close to `tokens.css` dusk by hand.
- The shard is drawn with background layers, so a shard cannot also have a
  background image or a `background-color` of its own. Set `--shard-fill`
  instead. Content that overlaps a cut corner is not clipped; keep padding at
  least `--shard-cut`.
