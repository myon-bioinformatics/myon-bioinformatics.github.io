# School world: desks, chairs, an emoji and a walk

An extension of the existing `web-ui-world/1` map, not a new engine. A floor may carry a **tile grid**
and **props**; the world may offer **avatars**. Everything stays in `scripts/world.py` on PySaiyanWeBoo's web UI (stdlib only, no server,
no storage, no new dependency). Worlds without these fields produce exactly the same HTML as before.

```python
import world                                       # scripts/world.py
spec = world.example_data("school")        # a classroom floor plus an open schoolyard
open("school.html", "w").write(world.world_document(spec))
```

## Data (all optional, additive)

| Field | Where | Meaning |
| --- | --- | --- |
| `tile` | floor | Tile size in map units: 16..128, a multiple of 8, dividing `width` and `height` |
| `props` | floor | Up to 512 `{kind, x, y, w, h}` rectangles, all on tiles and inside the floor |
| `kind` | prop | `desk`, `board`, `wall`, `shelf` are **solid**; `chair`, `rug` can be walked over (sit on a chair) |
| `avatars` | world | Up to 24 different labels offered first (emoji, short text such as `先生` or `A`, or both; 1..16 characters); the choice replaces every floor's player label |

| `classroom` | floor | `{rows, groups, per_group, tile}` (all optional) in place of `width`/`height`/`tile`/`props`: the floor is `classroom_floor(...)`. `id`, `label` and `spots`/`actors`/`player` may sit beside it and replace the generated ones |

A floor's `player` must start on a free tile. `classroom_floor(rows, groups, per_group=2, tile=32)` writes a whole classroom
floor (rows of desks, one chair under each, aisles, blackboard, teacher's desk, back shelves with a door gap) with every size a
multiple of the tile. A floor without `tile` keeps the old free walking.

## From another repository (one line)

A consuming repository keeps only JSON; Python makes the page (a Node script can run the same command).
`page -` reads the spec from stdin (at most 2 MB), so no temporary file is needed:

```
echo '{"schema":"web-ui-world/1","avatars":["🙂","🐱","🦊"],"floors":[{"id":"room","label":"教室","classroom":{"rows":5,"groups":3}}]}' \
  | python scripts/world.py page - > school.html
python scripts/world.py example school | python scripts/world.py page - > school.html          # the bundled example, as is
python -c "import sys;sys.path.insert(0,'scripts');import world as u;sys.stdout.write(u.world_document({'schema':u.WORLD_SCHEMA,'avatars':['🙂'],'floors':[{'classroom':{}}]}))"   # in-process
```

A bad spec exits with status 2 and one `error:` line on stderr (no traceback, nothing on stdout). Add `--theme NAME` for another theme.
Python, the CLI and `py_launch.cjs` return identical bytes; `tests/test_worlds.py` checks that.

## Who does what

* **Python** (`world_blocked`, `world_path`, `world_route_points`, `world_route`, `world_route_sample`) is the oracle: the
  walking grid, the shortest 4-neighbour path (breadth first, fixed neighbour order), and the chain of constant-speed segments.
* **The page** receives the grid as `data-blocked` (rows of `0`/`1`) and plays the same plan: `gridPath`, `gridRoute`,
  `motionRoute`, `routeSample`. Node tests compare them with Python on random cases.
* A goal that is solid, outside or cut off ends at the nearest reachable tile, so tapping a desk walks beside it.
  A tap on a reachable tile ends exactly where you tapped; keys and the pad move tile centre to tile centre.
* A route never leaves free tiles: between tile centres it stays inside two touching free tiles.

## Where things go (header, side, footer)

A grid world (or any world with `"shell": true`, or with `tools`) keeps the page short: nothing is stacked under the map, so a phone and a PC need no
vertical scrolling and nothing changes page. The screen is icons; the words are each button's `aria-label` and tooltip, in 11 languages (below).

* **Header** (the whole world): the info board, then 🏠 / ⭐ / ⚙️ and the emoji tools you add.
  * **🏠** home: first floor, everything in view, sheet and menus closed.
  * **⭐** favourites: a ☆ in the ☰ list stars a place; the ⭐ panel lists them (on any floor) and takes you there. They are a light cache: kept in this browser
    (`localStorage` key `ui-world:<id>`, only the starred places, the language and the name layer) and restored on the next visit. No dialog, no per-floor favourites, no export.
  * **🎒** bag (shown when any spot defines `item: {emoji, label, body?}`): the spot's sheet offers a button to add/remove the item, and the 🎒 panel lists collected items (kept in `localStorage` beside `fav`) with arrows back to each spot.
  * **⚙️** settings: ⏸️ pause the motion, 🙂✏️ change the emoji, 🌐 pick the language (a `<select>` of native names), 🏷️ the name layer (names / dots / off), 🔍 a dial for the zoom (turn it, or the wheel on the map turns it), 🫥 a slider for how see-through the controls over the map are (the pad, `data-overlay`; `--ui-overlay-alpha` .2–1, kept with the language).
* **Side** (this screen): 48px buttons that open a panel over the map (one menu open at a time; Escape, a tap on the map or choosing an item closes it).
  * **☰**: the places of this floor (and the category chips, if any). Each row has an arrow from you to the place (⬆️ ↗️ ➡️ ↘️ ⬇️ ↙️ ⬅️ ↖️, 📍 within one tile,
    🛗 when it is on another floor) that follows you as you walk; tap a row to go there and read its sheet. Works without JavaScript too (the rows are links).
  * **⋯**: 🚶 walk to X / Y and 🎯 find myself. Shown by the script.
* **Footer**: 🛗 the pulldown that moves between floors, each as it is, no door-to-door wiring needed. Without JavaScript the plain floor labels stand in for it.

Worlds without a tile grid keep the original layout and markup (floor chips on top, controls below) unless they ask for the shell.
A catalogue can too: `catalogue_world(items, shell=True)` turns a long list into floors you reach with the pulldown, with no scrolling.

### Your own icons: `tools` (an emoji is the key, the feature is the value)

```json
"tools": {
  "🗺️": {"label": "見どころ", "label_en": "Highlights", "spots": ["classroom-board", "flowers"]},
  "🏫": {"label": "学校", "body": "教室と校庭があります。"},
  "🛝": {"label": "校庭", "floor": "yard", "slot": "side"}
}
```

Each entry adds one icon with exactly one feature: `spots` (a panel listing those places, with arrows), `body` (a panel with a note), `floor` (a shortcut
to that floor), `href` (the icon is a link: a `./` `../` `/` path, a `#` fragment or an `https://` address) or `links` (a panel of up to 16 `{"label", "href"}` rows).
The chrome of a tool page (PySaiyanWeBoo's `chrome_html`, the same icons without a world: no floors) takes `href`, `links` and `body`. `slot` is `head` (default) or `side`; `label` (ja) / `label_en` (en) / `labels` (`{"fr": "Carte", "de": "Karte"}`, any of the other nine codes) are the tooltip words. Up to 8; the page's own icons (🏠 ⭐ ⚙️ 🌐 ☰ ⋯ 🛗) are taken.
Adding an icon is adding a key: nothing else in the page changes, and the key is the emoji itself.

How flutter_navigation_basic's header maps here (so it can be archived): Home → 🏠; Favorite this page / Favorites → ☆ and ⭐ (session only); Menu → ☰ ⚙️;
Language → 🌐 (labels switch, the content stays yours); Door-to-Door selector → 🛗 in the footer; the page's own action row → the emoji `tools`. Not taken over:
the "leave this page?" confirmation (a world has no unsaved page to lose; 🏠 has its own small ask() dialog) and favouriting a whole floor.

### Layers (🏷️)

A map is drawn in layers, back to front, like the z-order of a slide: the ground (props, `--ui-layer-ground`), the names (spot pills, `--ui-layer-name`),
the marks (dots and signs, `--ui-layer-mark`), the player and actors (`--ui-layer-player`), the sheet (`--ui-layer-sheet`). The world's `names` picks where
plain spots sit, and 🏷️ in ⚙️ switches it without a reload (kept with the language):

| `names` | plain spots |
|---|---|
| `names` (default) | every spot shows its name pill; crowded places overlap until you zoom |
| `dots` (the cities) | a dot in the mark layer; the spot the player stands by, the one under the pointer and the focused one show their names |
| `off` | dots only (the pointer and the focus still show a name) |

A spot's `mark` (one emoji) is drawn instead of the dot and leads the name when the name shows; `place_floor(marks={category: emoji})` (or `"marks"` in a
`place`) gives every point of a category its mark, and the world's `mark_scale: [x, y]` (0.5–4, default `[1, 1]`) sets the width and height factor of every mark,
dots included. The cities use 🎫 exits (ticket gates; 🛗 is the footer's), 🚉 stations and 🚆 termini at `[1.5, 1.5]`.
A spot with `always_named` stays in the name layer in every mode: its name shows faint behind the marks, the way a village's name lies on a land, and
🏷️ never turns it into a dot. `true` centres the name on the spot; `"left"` / `"right"` hang it on that side with the mark on the spot.
`place_floor(always_named=[category, ...])` (or `"always_named"` in a `place`) does it for every point of a category and hangs each name away from the
middle of the group, so the two sides of a station do not cover each other: Tokyo Station's six exits are always named (丸の内 to the left, 八重洲 to the right).
Signs (`sign`) always sit in the mark layer and keep their own dot → text → face cycle. While a sheet is open, the camera aims a little below the player or the spot,
so the thing you walked to stays in the view above the sheet.

### Dial (🔍)

`dial_html(name, minimum=, maximum=, step=, value=, label=, attrs=)` is a rotary dial over an ordinary `<input type="range">`: `DIAL_CSS` draws the knob and its
pointer (`--ui-dial-angle`, −135° to 135°), `bindDial(root)` from `dial.js` turns it by a drag around its centre or the wheel, and the input keeps the value, the keys,
the form and the aria-label, so a listener on `input`/`change` sees a dial and a slider the same way. The map's 🔍 is its first use; `dialAngle` and `dialValue` are the
pure maps between a value and an angle (`tests/test_pages.py` checks them in Node).

### Languages (🌐)

The chrome speaks the 11 languages of flutter_navigation_basic: ja, en, fr, es, pt, ar, zh, ru, id, de, sw (`world.WORLD_LANGS`, words in `WORLD_TEXT`, one tuple
per word in that order; a test checks every word in every language). Markup carries Japanese plus `data-t="<word>"`; 🌐 swaps `aria-label` and `title`, sets `lang`
on the world and remembers the choice. A tool of your own names itself with `label`, `label_en` and `labels`; a missing language falls back to English, then Japanese.
The content (spot labels, bodies, the board) is yours and is not translated. Arabic changes the words only: the map is not mirrored.

## Lands: other spaces from the same grid

A land is a floor made of terrain instead of furniture, so a world can be a Dragon Quest-style map of several lands (`EXAMPLES["overworld"]`,
six lands, a few lines of JSON) and the footer's 🛗 pulldown moves between them. Nothing links one land to another.

```json
{"schema": "web-ui-world/1", "id": "trip", "floors": [
  {"id": "north", "label": "北", "land": {"theme": "castle"}},
  {"id": "sea", "land": {"theme": "coast", "cols": 24, "rows": 16, "seed": 5, "tile": 32}}]}
```

* `theme`: `meadow 🌱`, `forest 🌲`, `mountain ⛰️`, `desert 🏜️`, `coast 🌊`, `castle 🏰` (`LAND_THEMES`: each swaps the ground, the edge, the scattered
  object, the pond, how many houses). The same arguments always give the same land; `seed` makes another. `cols` 12..48, `rows` 12..32, `tile` a multiple of 8.
* Each land has a road from the player's start to a village crossroads, and two spots (the town; a landmark on the nearest bank of the water, else the
  farthest tile) on tiles that can be walked to. `spots`, `actors` and `player` beside `land` replace the generated ones, like `classroom`.
* From Python: `world.land_floor(theme, cols, rows, seed=, tile=, id=, label=)`; from another repository: `... | python scripts/world.py page - > lands.html`.

The representation changes by swapping objects, not code: the prop kinds of any floor can be mixed.

| Kind | Walk | Looks like |
|---|---|---|
| `grass` `sand` `road` `bridge` (ground) | yes, and they **open** the tiles under them (a road through trees, a bridge over water) | a colour |
| `water` `tree` `cactus` `mountain` `house` `castle` | blocked | 🌊 🌲 🌵 ⛰️ 🏠 🏰, one per tile (the castle once across its prop) |
| `fire` | free (decoration) | 🔥, one per tile |
| `desk` `board` `wall` `shelf` / `chair` `rug` | blocked / free, as before | the classroom's theme-coloured shapes |

`WORLD_PROPS` (blocks walking), `WORLD_GROUND` (opens) and `WORLD_LOOK` (colour, emoji, once) are the whole table; the CSS is written only for the kinds a
world uses. A new kind is one line in each.

## Places: real space in miniature

A `place` floor lays **real positions** (latitude and longitude) on the same grid, so a world can go on from a village to a real city in its other
form (`EXAMPLES["cities"]`): **Parallel Tokyo**, Tokyo Station with its six exits and the stations around it; **Reverse London**, the main termini and the
stations beside them, the Thames and a wooden `nogard` sign (dragon, backwards) that turns into 🐉 when pressed; **Fake Paris**, the main stations,
the metro beside them and the Seine, with a 🔥 in each block. The cities are their transport only (no sights, no institutions), so every name fits on the map. Nothing is drawn to look like the place: ground, roads, water and bridges are the same kinds as a land.

```json
{"schema": "web-ui-world/1", "id": "trip", "floors": [{"id": "tokyo", "label": "TOKYO", "place": {"meters": 32, "points": [
  {"id": "marunouchi-c", "label": "丸の内中央口", "lat": 35.68134, "lon": 139.7665, "category": "exit", "body": "…"},
  {"id": "yurakucho", "label": "有楽町", "maps": "https://www.google.com/maps/@35.6751,139.763,17z", "category": "station"}],
  "links": [["marunouchi-c", "yurakucho"]]}}]}
```

* `points`: 1..64, each with `id`, `label`, `category` and `body` (as a spot has) and **either** `lat` and `lon` **or** `maps`, a Google or Apple Maps URL read
  by the page's own coordinate tool (`try_parse_maps_url`). `flip` (a short text or emoji) is a second face: pressing the pill swaps it with the label, and again
  swaps back (a spot of any floor can have one; without script it stays a plain label).
* `sign`: `"led"` (amber on black, monospace: an electronic board) or `"wood"` (a wooden board). It is **a bold dot (●) until it is touched**, then the board shows its
  text; touched again it shows its `flip` face if it has one (nogard → 🐉), and then the dot again. On a spot of any floor it is only
  the look; on a place point it also puts the spot on the **nearest tile corner** (the four corners of a square are points of the grid too), so a sign takes no
  tile, sits between the stations, two signs never share a corner, and it must touch a tile that can be walked on (the player walks to the tile beside it).
  Signs make small notices: a direction board between the exits, a wooden sign with a `flip` (nogard ⇄ 🐉). A place needs at least one point that is not a sign
  (the player starts on it). A point is a spot on the tile its position falls on; `meters` (8..2000, default 64) is the ground
  one tile covers, and the north is up. The player starts at `start` (a point id, default the first point).
* The map is the points' box plus two tiles all round, or `area: {"center": [lat, lon], "radius": metres}`: the box `tolerance_area` gives (a point outside it
  is an error). The scale and the radius are the ones of the coordinates tool (`EARTH_RADIUS_M`, `parse_coordinate`); the projection is flat, good for a few kilometres.
* `links`: pairs of point ids joined by an L-shaped road. `rivers`: `{"line": [[lat, lon], ...], "width": tiles}` bands of water; **a road that crosses one is a
  bridge**, and a point that water cuts off from the start is an error naming it (add a link), so every spot can be walked to.
* `scatter`: `{"kind": "fire", "every": 8, "seed": 5}` cuts the map into blocks of `every` tiles and puts one `fire` (a decoration you walk over: `WORLD_PROPS`
  false, `WORLD_LOOK` 🔥) on a free tile of each, never on a road, the river or a spot; the same arguments give the same fires.
* Two points on one tile: the earlier keeps it and the other goes to the nearest free tile (never into water). Roads and water are merged into rectangles, so a
  place stays far below the 512-prop limit.
* The coordinates in `EXAMPLES["cities"]` are approximate (about 100 m, read off public maps): a miniature shows where things stand relative to each other, not exact positions.
  There are no facility names in TOKYO, only stations and exits, and no religious buildings in any of the three cities (`tests/test_worlds.py` keeps it so).
* Evidence: `tests/world_browser.py` (`CitiesTests`) walks to every spot of the three cities on a phone and a desktop, touches every sign, and checks the
  tools, keys, categories, favourites, six widths, eleven languages and the page without JavaScript. With `WORLD_SHOTS=DIR` it also keeps a WebP of each check with
  a `manifest.json` and an `index.html`; the reviewed set lives in PySaiyanWeBoo's [`docs/evidence/cities-<date>/`](https://github.com/myon-bioinformatics/PySaiyanWeBoo/tree/3af5ef36a9b44de1481b520e15c2b063c7848c47/docs/evidence) (kept there). The three `cities-*.gif` demos are the same operations in motion.
* From Python: `world.place_floor(points, meters=, tile=, links=, rivers=, area=, start=, id=, label=)`; from another repository: `page -` with `place` as above.
  The cities open in the **dots** name layer (below), so the crowded centre is dots, not a pile of names; `"names": "names"` on the world shows every name.

## Real × virtual (🖼️📷)

`"real": true` on a floor (also beside a `land` or `classroom`) lets the visitor put **a photo they choose or their camera** behind that floor's props, spots and
player. It is shown in the page and nothing else: a photo is an object URL on an `<img>`, the camera a stream on a `<video>`; neither is drawn, read back,
recorded, stored (not even in the ⭐/🌐 cache) or sent, and the guard test in `tests/test_pages.py` pins that. The camera is released by 🧹, by
leaving the floor, or by closing the page; a refused or missing camera says ⚠️ and the floor stays plain.

* On a real floor the ⋯ menu has one button, 🖼️📷. It opens the shared dialog (below) with 📷 camera, 🖼️ photo, 🧹 clear (only once something is shown) and ✖️.
* Props are drawn over the picture, so a props-free floor (`EXAMPLES["overworld"]` ends with one) shows the picture whole, and a floor with a few solid props
  (a house, a tree) puts them on top of the room. The walk grid is the same grid either way.
* Words: `backdrop`, `camera`, `photo`, `clear`, `unavailable` in the same 11 languages as the rest of the chrome.

### `ask()`: the one dialog for choosing or confirming

`el.ask(glyph, choices, t?)` (`el` is the world element `bindWorlds()` returns) shows icons and resolves with the chosen value, or `null` for ✖️, Esc or a tap outside:

```js
const answer = await world.ask('🖼️📷', [{glyph: '📷', t: 'camera', value: 'camera'}, {glyph: '🖼️', t: 'photo', value: 'photo'}], 'backdrop');
```

A choice is `{glyph, t, value}`; `t` names a catalogue word (so the label is the aria-label and tooltip in the visitor's language) and the optional third
argument labels the dialog. The look is the emoji picker's (one CSS rule set), keys do not walk the player while it is open, and opening another replaces it. 🏠 uses it too: it asks
first (🏠 goes, ✖️ stays), because home resets the floor, the filter and the sheet: `ask('🏠❓', [{glyph: '🏠', t: 'home', value: true}], 'home')`.

A second direction is not built: depth instead of one flat plane, layers at different depths (parallax) so the space reads as more than two axes. It would be additive on the same props and spots.

## Direction arrows (two positions, one arrow)

`world_point(rect, at)` takes the centre (`center`), the middle of an edge (`left` `right` `top` `bottom`) or a corner (`top-left` ...) of an object;
a spot or a person is a rect with no size. `world_direction(a, b, eps=8)` returns the arrow from `a` towards `b` (screen y grows downward, so a target above and to
the right is ↗️), or 📍 when both axes are within `eps`. It uses an integer slope (5/12, about 22.6°) instead of trigonometry, so Python and the page's `direction`
agree on every input (a Node test compares them on random points). `world_arrow_anchor("↘️")` goes the other way: an arrow, plain or emoji form (`↘`, `⬅`, `←`),
names an anchor (`bottom-right`); `🎯` and `📍` mean the centre. The recorder's `cam.zoom("↘️")` uses the same table.

## Moving (phone and PC)

* **Tap / click** a blank place or a spot: walk there around the furniture.
* **Arrow keys or WASD**: one tile at a time; hold to keep walking (the map must have focus; typing in a field never moves you).
  On a floor without a grid the keys are left to the page.
* **On-screen pad** (▲◀▶▼, 48px buttons, over the map's lower left): press and hold to keep walking; keyboard activation (Enter / Space) steps once.
* **🎯 自分の場所** (⋯ menu): zoom to yourself and keep the camera on you. Dragging the map stops the following.
* **X / Y form** (🚶, ⋯ menu) and the stop button (⏸️, ⚙️ menu) from the base world remain.

## The emoji comes first

With `avatars`, the world opens with a picker (a plain `div` in the map, shown by the script, not a modal): choose one of the
listed characters or type your own: an emoji, a short text such as an initial or a name, or both (`🐱たろう`), 1..16 characters.
In `avatars` and the `player` the same rule holds: control and line-separator characters, bidirectional overrides and spaces at either end are
refused; the label is set as text, never as markup. (`actors` and catalog pages keep the stricter emoji-only rule.) The player stays hidden until then. **🙂✏️** (⚙️ menu) reopens it. The emoji and the board messages are never stored; a reload
asks again. Without JavaScript the picker, the pad and the player controls stay hidden and the static map and spots still work.

## RPG & Gamification (`rpg`)

Worlds that set optional `"rpg"` (`EXAMPLES["overworld"]`, starting in `meadow` / はじまりの村) layer an offline, pure-JS turn-based RPG and gamification system over the same map, `🎒` bag, and `PySaiyanWeBoo` orb readout primitives (`play_random`, `counter_effect`, `counter_label`):

* **Contact dialogue (`npcs`)**: Walking within tile contact range of village NPCs (or tapping them) opens multi-page dialogue with optional healing (`heal`), shop purchases (`shop`), and 3-choice portfolio/GitHub quizzes (`quiz`).
* **Ground drops & chests (`loot`)**: Collecting ground drops (`🌿`, `💧`, `📜`) or chests (`🎁` → `📭`, optionally gated by `requires_enemy`) syncs `.ui-world-take` into `🎒` and applies gear (`ATK`/`DEF`/`MaxHP`/`MaxMP`) or consumables.
* **Turn-based battle (`enemies`, `skills`, `orbs`)**: Five commands (`⚔️`, `✨`, `🎒`, `🛡️`, `💨`), telegraphed 3-turn heavy enemy strikes, PSWB attribute/heal orb animations, EXP/Lv/Gold, and an Adventure Journal modal (`📜`) tracking quests, badges, equipment, and the bestiary.

## Fake Paris Firefighting Hero & Gamification (`rescue`)

Worlds that set optional `"rescue"` (`EXAMPLES["cities"]`, active on the Fake Paris floor `#paris`) provide a dedicated Firefighting Hero × Gamification experience scoped to Paris's 36×38 tile grid and 25 scattered fire props:

* **Contact canned dialogue (`nodes` / `npc`)**: Walking within tile contact range of Paris NPCs (or clicking them) opens multi-page lore and assistance without interrupting navigation:
  - **👩‍🚒 マルゴ隊長** (`(24, 5)`): Hero briefing on firefighting, water tank management, and city greening.
  - **📡 通信士エミール** (`(28, 7)`): Lore on `TalkCompress` & `cli_args` protocol design and the `🧭` fire radar.
  - **🥐 パン職人コレット** (`(12, 7)`): Medal shop exchanging firefighting medals `🪙` for fresh croissants `🥐`, high-pressure water cylinders `🧯`, and cryo gel bombs `🧊`.
  - **🧑‍🔧 水路技師クロード** (`(27, 24)`): Lore on `FluidFullSpeedSimulation` & `DRAgoWing` hydrodynamics; instant full HP and water tank refill.
  - **📚 記録官ルネ** (`(21, 29)`): 3-choice quizzes covering `PySaiyanWeBoo`, `FluidFullSpeedSimulation`, `TalkCompress`, `OnTautoLogy`, `BrowserTestKit`, and `CaChereCyCle` with medal/EXP rewards.
  - **🧑‍✈️ 駅長ベルナール** (`(5, 33)`): Guidance on Left Bank boss fire `(21, 31)` and sealed equipment.
* **Ground drops & treasure chests (`drops`, `chests`)**: Walkable ground items (`🧯`, `🥐`, `🧊`, `🥖`, `🌡️`) and treasure chests (`🎁` → `📭`, including a 3-fire sealed golden helmet chest) that grant permanent gear bonuses (`🚿 Power`, `🛡️ Shield`, `❤️ MaxHP`, `💧 MaxWater`) and sync into the world `🎒` Bag.
* **Firefighting Hero × Gamification (blazes, orbs & greening)**:
  - **Blaze tiers**: 25 scattered blazes range from Lv.1 小火スパーク to Lv.2 延焼ブレイズ and the Lv.3 大火災インフェルノ boss.
  - **Smooth auto-splash on the move**: Walking onto or adjacent to a Tier 1 fire with `water >= 6` automatically extinguishes it with a non-blocking toast and plants a `GARDEN_GLYPHS` bloom on the tile without modal interruption.
  - **Tactical firefighting modal**: Tapping a blaze or engaging higher-tier fires opens the interactive firefighting view (`🚿 放水ジェット`, `🌊 高圧スプラッシュ`, `❄️ 冷却ミストバリア`, `🎒 どうぐ`, `💨 退避`) with cooling/heat orb bursts (`rescueOrbEffect`), heat flare retaliation, and water pressure management.
  - **Greening blooms & Hero Journal (`counter_garden`)**: Each extinguished fire plants a bloom (`🌱`, `🌷`, `🌳`, `🍄`, `🌻`, `🪨`) via PySaiyanWeBoo's deterministic `counter_garden`, viewable on an 8×8 (64 cells) greening grid inside the Hero Journal (`📋`), unlocking souvenir stamp badges.
  - **Nearest-fire compass radar (`world_direction`)**: The HUD compass (`🧭`) continuously computes distance and direction to the nearest unextinguished fire; clicking it dispatches the hero toward that fire.

## Not included

## Demos

Each GIF (`<world>-<scene>.gif`) is a real run of the generated page in Chrome, recorded by `scripts/world.py record` (Playwright keeps a screenshot with its real
time whenever a scene waits; Pillow writes one shared palette and delta frames). They are regenerated, never edited by hand:

```sh
WEB_UI_CHROME=/path/to/chrome python scripts/world.py record media/world --force            # all scenes
python scripts/world.py record media/world --only keys tap --force --width 400               # some, smaller
python scripts/world.py record runs --prefix ci- --suffix=-chrome --timestamp --git-commit # runs/ci-school-pick-chrome-20261108T113412Z-288cbed.gif …
python scripts/world.py record runs --git-commit --timestamp                               # runs/school-pick-288cbed-20261108T113412Z.gif …
```

File names are `<prefix><world>-<scene><suffix>`, then the run details. `--prefix` and `--suffix` (letters, digits, `_ . -`; write
`--suffix=-x` when it starts with `-`) are optional: the prefix is always leftmost and the suffix right after the base name, wherever they are given
on the command line. The run details are added left to right in
the order their options are given: `--timestamp` adds when the run started, in UTC as ISO 8601 basic format (`20261108T113412Z` is 20:34:12
in Tokyo), so names sort in recording order and read the same in any time zone; `--git-commit` adds the git commit the pages were built from
(`288cbed`, or `288cbed-dirty` when tracked files have uncommitted changes). A repeated option adds nothing. Every scene of one run shares
the same timestamp and commit. Without `--timestamp` an existing file is refused unless `--force`, so a repeated run by hand or by an agent
either keeps its own files or says so. `pysaiyanweboo.add_gif_arguments`, `gif_targets` and `gif_targets_from` are these rules as functions
(scripts/world.py imports them from PySaiyanWeBoo; `ext=".png"` names stills, so other recorders such as BrowserTestKit's evidence_gif can share them):
the browser tests name their GIFs through them from `PSWB_GIFS="DIR [--prefix P] [--suffix S] [--timestamp] [--git-commit] [--force]"`.

| File | Shows |
|---|---|
| `school-pick.gif` | the picker comes first; choosing 🦊 puts it in the room |
| `school-avatar-text.gif` | **🙂✏️** (in ⚙️), then typing text and an emoji (`先生🍎`) as the character |
| `school-keys.gif` | arrow keys and WASD, a held key repeating, desks stopping the walk |
| `school-tap.gif` | tapping a chair (the path goes around the desks) and tapping a desk (nearest free tile) |
| `school-phone.gif` | a phone-sized screen: tap a character, the on-screen pad, drag the map away, **🎯** (in ⋯) |
| `school-menu.gif` | the ☰ list with its arrows; tap **黒板** and the arrow turns into 📍 as you arrive |
| `school-header.gif` | the header: ⭐ stars on two floors and their list, the 🗺️ tool, 🌐 the language, 🏠 home |
| `school-floors.gif` | the footer pulldown to the schoolyard, a spot's sheet, back to the classroom, the board spot |
| `overworld-lands.gif` | six lands by the 🛗 pulldown (forest, mountain, desert, coast, castle), then walking to the castle town from the ☰ list |
| `overworld-real.gif` | the real floor: ⋯ → 🖼️📷 → 🖼️ choose a photo, walk over it, then 🧹 (the photo is drawn by the recorder) |
| `cities-tokyo.gif` | Parallel Tokyo: the 🚉 tool (the six exits of Tokyo Station), Marunouchi to Yaesu through the concourse, the electronic board's dot and text, on to Kanda by ☰ |
| `cities-london.gif` | Reverse London: 🎡 in the header, King's Cross to Waterloo over the Thames bridge, the wooden **nogard** board: dot, text, 🐉, dot |
| `cities-paris.gif` | Fake Paris: 🥖 in the header, a 🔥 in each block, west from Gare du Nord to Saint-Lazare |
| `school-oneliner.gif` | the one command from another repository; the byte count and time shown are that run's real output |

A scene may end with `cam.zoom((x, y))` (or an anchor name or arrow emoji such as `cam.zoom("↘️")`): a smooth zoom toward that point that stays (the easing of Ironmate's `png_zoom_gif.py`, taken into this
tool and written by the same encoder rather than kept as a second tool), because the README shows the GIFs small.
The frames are cropped to the world, not the whole page. A new operation is one `@scene` function in the tool. `tests/world_browser.py` records every scene, so a UI change that breaks a demo
fails the browser job instead of leaving a stale GIF. The page asks for Meiryo first; these were recorded on Linux, where it is absent, so the fallback
face shows (record on Windows to get Meiryo).

Other people's avatars. Showing several visitors at once needs a server or peer connection, which this static layer
deliberately does not have. The shared GitHub board (`docs/world-shared-board.md`) remains the only shared channel.

## Verification

```
PYTHONPATH=. python -m pytest -q tests/test_worlds.py          # oracle, validation, generator, HTML, Node 26 parity
PYTHONPATH=. python -m pytest -q tests/test_worlds.py             # projection, bridges, nudging, scatter, flip, the three cities
WEB_UI_CHROME=/path/to/chrome python tests/world_browser.py -v   # real browser: picker, keys, pad, taps, no desk crossing, 320..1280px
```
