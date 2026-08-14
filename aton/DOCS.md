# Aton

Renders LED matrix displays from a YAML description and sends them to WLED.

This page is the short reference. The full documentation, with screenshots, lives in the
repository:

- **Getting started** — `docs/getting-started.md`
- **YAML reference** — `docs/yaml-reference.md`
- **The configurator** — `docs/configurator.md`
- **A complete example to copy** — `examples/aton.yaml`

## The description file

The app reads one file from the configuration folder, `aton.yaml` by default.

**Two ways to change it:**

1. **The configurator** in this app (tab *Configuration*). It covers everything described
   here and reloads by itself after saving.
2. **Directly in an editor** (`/config/aton.yaml`), then restart the app — that takes
   seconds, not a Home Assistant restart.

Both get along: the configurator keeps your comments and refuses to save if the file was
changed elsewhere in the meantime.

Next to the heading every page shows the **build**: app version and modification time of
the UI, e.g. `0.10.5·1786111641`. If that does not match what you expect, your browser is
showing an old copy — reload hard (Ctrl-Shift-R / Cmd-Shift-R).

## Skeleton

```yaml
defaults:
  font: 5x3
  color: ffffff
  interval: 5

panels:
  - id: living_room        # becomes part of the entity IDs
    name: Living room matrix
    host: 192.168.1.50
    size: [128, 64]
    interval: 5            # seconds between two frames — one "cycle"
    full_frame_every: 60   # every N frames a full frame as a recovery point
    led_pitch: 3.0         # pixel pitch in mm — DISPLAY ONLY
    dry_run: false         # true = compute and preview, but send NOTHING

    grid: {row_height: 9, col_width: 32, icon_width: 8, gap: 1}

    gate:                  # when to draw at all
      entity: light.matrix_power
      fallback: switch.matrix_relay
      script: script.toggle_matrix        # optional
      wartezeit: 90                       # s to wait for the gate before sending anyway
    brightness:
      entity: input_number.matrix_brightness   # omit → own slider in HA
      default: 128

    widgets: [...]         # base image
    screen_groups: [...]   # areas that change
    notify: {...}          # notification row (old form; today a `type: notify` tile)
```

Only the **changed** pixels are transmitted; every `full_frame_every` frames a full frame
follows as a recovery point.

## Operations

The *Operations* tab has one card per panel, with preview, an on/off button, a brightness
slider, the screen selectors and a list of values.

- **`gate`** decides whether Aton draws. Without `script` the app switches the gate
  directly. A script is needed when the controller shares power with the panels — the
  ordering (boot first, then enable the config entry) belongs in Home Assistant.
- ⚠ A `fallback` pointing at an entity that does not exist counts as **off**, and nothing
  is drawn. Without any fallback, an unusable gate falls back to drawing.
- ⚠ **Drawing is not sending.** The gate and the fallback answer "may I draw?"; whether the
  device *answers* is a different question. Mains power is present long before WLED is on
  the network — measured on one installation: 18 s, 20 s, once 95 s. Aton therefore sends
  only once the gate itself reports `on`, waits `gate.wartezeit` (default 90 s) and then
  tries anyway — that single attempt is what recovers a lost segment. While unreachable it
  backs off (10, 20, 40, 60 s) but keeps rendering, so the preview stays live.
- **Brightness** without `brightness.entity` does **not survive a restart**. An
  `input_number` keeps it and makes it automatable.
- ⚠ A brightness change sends a **full frame**: on a frozen segment the value alone does
  not change a standing image, the pixels have to be written again. Aton sets the
  **segment** brightness, not WLED's global one — the two multiply.
- **Send errors** count frames that failed *although* Home Assistant considered the device
  reachable. Attempts made while the gate is not yet `on` are probes; they set
  "not reachable since …" but are not counted.

## Widgets

Position through the grid (`cell: [row, column]`) or absolutely (`at: [x, y]` with
`size`).

Types: `tile` (default), `text`, `icon`, `image`, `rect`, `calendar`, `clock`, `clock_wd`,
`notify`, `icons`, `series`.

Two keys apply to all of them: `layer` decides the drawing order (everything is on 0 and is
drawn in list order — a higher layer lands on top), `visible_when` is a Jinja condition that
skips the tile.

Text comes from exactly one source: `value` (plus optional `attribute`, `format`,
`decimals`, `scale`, `unavailable`), or `text`, or `template`.

Icon and colour understand four forms: a fixed name, `map` (exact match), `steps`
(threshold ≥) and `template`.

⚠ `on` and `off` need quotes in `map:` — `map: {"off": dry, "on": wet}` — otherwise YAML
turns them into booleans and the comparison against a state string fails.

## Icon lists

`type: icons` draws a list of icons into its area; the names come from the text source
(`template`, `value`, `text`), separated by commas or whitespace. Wrapping is automatic,
all cells are the same size so the columns line up, and an unknown name is skipped and
reported instead of costing the whole tile. `spacing` sets the gap, `align` the row
alignment, `cell_size` a fixed cell.

## Column series

`type: series` draws columns from one template — `"14|@w_sun|21°, 15|@w_rain|20°"`,
columns separated by commas, the rows of a column by `|`. A part prefixed with `@` is an
icon, everything else is text, so any arrangement works: two rows of text, one row of
icons, an icon above a label. `row_colors` and `row_fonts` style each row separately (position = row, empty = as the tile). Cells are all the same width so the columns stay flush; `spacing`, `align`,
`cell_size`, wrapping and the missing-icon report work as for `icons`.

## Your own widget types

Set the add-on option `custom_widgets: true` and drop Python files into
`/homeassistant/aton_widgets`. Each one declares a type with its own fields, which are then
validated on load and offered as a form in the configurator:

```python
from aton_api import Feld, widget

@widget("dot", felder=[Feld("sensor", "entitaet", "Sensor", pflicht=True)])
def zeichne(bild, w, ctx):
    farbe = "30c030" if ctx.state(w.optionen["sensor"]) == "on" else "802020"
    ctx.zeichner(bild).rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1],
                                 fill=ctx.rgb(farbe))
```

⚠ The option is **off by default**: unlike `aton_fonts` and `aton_icons`, this directory
holds code that gets executed. A broken plugin costs its own tile and nothing more —
the message names the file. Full guide: `docs/custom-widgets.md` in the repository.

## Screen groups and pages

An area whose content is exchanged; each group becomes a selector
`Automatic | <screen> | …`. **Automatic** takes the first screen whose `when` is true;
picking by hand in HA beats `when`.

A screen may hold **pages** (`pages`) that take turns while the selector still shows the
screen. `page_cycles` is the master switch and the default duration;
`cycles` per page overrides it, `0` means "as the screen says". One cycle is one
`interval`.

## Notifications

A message line is a tile: `type: notify`, placed like any other and empty while nothing is
pending. Give it `layer: 1` so it is drawn above the screen groups.

`aton.notify` (fields `text`, `level`, `duration`, `id`, `channel`, `panel`) fills it;
`aton.notify_clear` removes it (by `id`, by `channel`, or everything). Short text is a
static bar, longer text uses WLED's own marquee — and since the device has only one
scrolling segment, only the first line can scroll.

Several lines are possible: one with `channel: warnings` takes only messages of that
channel, `show_levels: warning` narrows it to a level. A line without a channel is the
main line and also catches messages whose channel has no line at all.

The old per-panel block `notify: {region: [...]}` still works — it is translated into such
a tile while loading. The configurator offers *Convert to tile* on it.

## Fonts and icons

Shipped: `5x3`, `matrix5x3`, Spleen and Terminus in several sizes. Your own go into
`/homeassistant/aton_fonts` (`.pil`, `.bdf`, `.pcf`, `.ttf`, `.otf`; vector fonts need
`font: mine@8`).

47 icons are built in. Your own PNGs go into `/homeassistant/aton_icons`, or you draw them
in the *Icons* tab. A file overrides a built-in icon of the same name.

## Templates

Jinja against the app's own state mirror: `states`, `state_attr`, `is_state`,
`is_state_attr`, `has_value`, `now`, `utcnow` and the usual filters.

⚠ This is a **subset** of Home Assistant's templating — no device resolution, no `expand`,
no `area_*`, no history. Build a template sensor in HA if you need those.

⚠ Most common mistake: `states('sensor.x') | round(0)` raises when the entity is missing,
because `states()` returns the string `unknown`. Filter first: `| float(0) | round(0)`.

## Entities in Home Assistant

The app creates none by itself. The companion integration (HACS) provides, per panel, one
device with a selector per screen group, a preview image, diagnostic sensors, a full-frame
button and — without `brightness.entity` — a brightness control. No MQTT is involved.

Without the integration the app keeps working; you operate it from this page.
