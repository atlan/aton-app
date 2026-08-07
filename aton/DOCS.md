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
    brightness:
      entity: input_number.matrix_brightness   # omit → own slider in HA
      default: 128

    widgets: [...]         # base image
    screen_groups: [...]   # areas that change
    notify: {...}          # notification row
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
- **Brightness** without `brightness.entity` does **not survive a restart**. An
  `input_number` keeps it and makes it automatable.

## Widgets

Position through the grid (`cell: [row, column]`) or absolutely (`at: [x, y]` with
`size`).

Types: `tile` (default), `text`, `icon`, `image`, `rect`, `calendar`, `clock`.

Text comes from exactly one source: `value` (plus optional `attribute`, `format`,
`decimals`, `scale`, `unavailable`), or `text`, or `template`.

Icon and colour understand four forms: a fixed name, `map` (exact match), `steps`
(threshold ≥) and `template`.

⚠ `on` and `off` need quotes in `map:` — `map: {"off": dry, "on": wet}` — otherwise YAML
turns them into booleans and the comparison against a state string fails.

## Screen groups and pages

An area whose content is exchanged; each group becomes a selector
`Automatic | <screen> | …`. **Automatic** takes the first screen whose `when` is true;
picking by hand in HA beats `when`.

A screen may hold **pages** (`seiten`) that take turns while the selector still shows the
screen. `wechsel_zyklen` is the master switch and the default duration;
`zyklen` per page overrides it, `0` means "as the screen says". One cycle is one
`interval`.

## Notifications

`aton.notify` (fields `text`, `level`, `duration`, `id`, `panel`) writes into the
`notify` region; `aton.notify_clear` removes it. Short text is a static bar, longer text
uses WLED's own marquee.

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
