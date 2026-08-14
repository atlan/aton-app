# YAML reference

Aton reads one file from the configuration folder (`aton.yaml` by default). Everything
here can also be done in [the configurator](configurator.md).

A complete, commented example to copy: [`examples/aton.yaml`](../examples/aton.yaml).

## Skeleton

```yaml
defaults:            # optional, applies to every panel
  font: 5x3
  color: ffffff
  interval: 5

fonts:               # optional — properties of the font, not of the program
  matrix5x3:
    uppercase: true      # lowercase is unreadable at 5 px
    transliterate: true  # Ä→AE, Ö→OE, Ü→UE, ß→SS (no room for dots)

panels:
  - id: living_room        # becomes part of the entity IDs
    name: Living room matrix
    host: 192.168.1.50
    size: [128, 64]
    interval: 5            # seconds between two frames — one "cycle"
    full_frame_every: 60   # every N frames a full frame as a recovery point
    clear_segments_to: 32  # how far old segments are cleared on a full frame
                           # (WLED's MAX_NUM_SEGMENTS, usually 32 on ESP32)
    led_pitch: 3.0         # pixel pitch in mm (P3 = 3.0) — DISPLAY ONLY
    dry_run: false         # true = compute and preview, but send NOTHING

    grid: {row_height: 9, col_width: 32, icon_width: 8, gap: 1}

    gate:                  # when to draw at all
      entity: light.matrix_power
      fallback: switch.matrix_relay
      script: script.toggle_matrix        # optional, see below
    brightness:
      entity: input_number.matrix_brightness   # omit → own slider in HA
      default: 128

    widgets: [...]         # base image
    screen_groups: [...]   # areas that change
    notify: {...}          # notification row (old form, see below)
```

Normally only the **changed** pixels go to the device. Every `full_frame_every` frames a
full frame follows as a recovery point — it describes the whole surface including the
black parts, and therefore also takes back a pixel that does not belong there (after a
WLED restart, or someone else writing to the panel).

⚠ The full frame does **not** clear the surface first. Doing that blanked the matrix
visibly — at 60 frames and a 5 s cycle, a flicker every five minutes. Completeness of the
encoding is what replaces it.

## The gate — when Aton draws

```yaml
gate:
  entity: light.matrix_power     # the real off switch of the display
  fallback: switch.matrix_relay  # decides on/off when the gate is missing or unavailable
  script: script.toggle_matrix   # optional: what the on/off button triggers
  wartezeit: 90                  # seconds to wait for the gate before sending anyway
```

Without `script` the app switches the gate directly (or the fallback, when the gate is
missing because the device has no power).

### Why `fallback` exists

WLED's master switch is the real off switch. Home Assistant only creates it while the
device has **more than one segment**. If the segment list shrinks, it goes `unavailable` —
and without a fallback nothing would ever be rendered again, even though rendering is
exactly what restores the segments. Only in that case does the power switch decide.

### Drawing is not sending — `wartezeit`

The fallback answers "may I draw?". Whether the device *answers* is a different question,
and the gap between them is real: after switching on, mains power is present long before
WLED is on the network. Measured on one installation: **18 s, 20 s and once 95 s** between
the power switch and the gate reporting `on`.

Aton therefore sends only once the gate itself reports `on` — Home Assistant sets that
exactly when it is talking to the device, so the reachability check already exists and
costs nothing. `wartezeit` (default 90 s) is how long to wait before trying anyway; that
single attempt is what resolves the segment loss described above. If your boot takes
longer, raise it — the cost of a value that is too low is one attempt plus a back-off, not
a broken display.

While the device stays unreachable, Aton backs off (10, 20, 40, 60 s) and keeps
**rendering** in the normal cycle, so the preview stays live. A frame is abandoned after
the first block that fails, and an attempt made while the gate does *not* say `on` counts
as a probe: it sets the reachability state but is not counted as a send error. Only a
failure while HA considers the device reachable is one.

⚠ **A fallback that does not exist counts as "off".** If you point `fallback` at an entity
you have not created yet, nothing is drawn and the panel stays dark. Without any fallback,
an unusable gate falls back to drawing.

### When a script is necessary

If the controller shares power with the panels, "socket on" is not enough. It has to boot
and join the network *before* Home Assistant may enable its config entry — otherwise setup
fails against an unreachable device and HA then backs off with growing intervals. On the
way out, the connection has to go *before* the power, or HA logs connection errors. That
ordering, with the measured waits, belongs in an HA script — enabling a config entry is
not something a rendering app should do.

⚠ A script has no notion of "off": the app starts it with `script.turn_on`, and the script
decides from the current state which way to switch.

## Brightness

The slider writes where the brightness is also **read** — to `brightness.entity`
(`input_number` or `number`) when configured, otherwise to a value inside the app.

⚠ Without an entity the value **does not survive a restart**; it falls back to
`brightness_default`. An `input_number` keeps it and makes it automatable — that is the
reason to configure one.

⚠ A brightness change sends a **full frame**. On a frozen segment the segment brightness
only takes effect once the pixels are written again — the value on its own does not change
a standing image. On a panel whose content moves this would happen on the next cycle
anyway; on a static one (a to-do list, a forecast) it would never happen, and the slider
would look broken. The cost is one full frame per slider move, and only then.

⚠ Aton sets the **segment** brightness, not WLED's global one. The two multiply, so the
value in WLED's own UI stays and still applies. That is deliberate: the global slider
belongs to you.

## `led_pitch` — display only

The pixel pitch in millimetres (P3 = 3.0). It affects only how the preview is drawn, never
what goes to WLED:

- **Scale:** the preview is scaled relative to it, so two panels appear in their true size
  relation. A 64×128 at P2.5 is physically 160 × 320 mm and is drawn smaller than a
  128×64 at P3 (384 × 192 mm).
- **Look:** the LEDs appear as dots instead of touching squares.

Without an entry everything stays as before — full zoom, thin pixel grid. The reference is
P3: a P3 matrix is drawn at exactly the requested zoom, a finer one smaller, a coarser one
larger.

## Widgets

Position either through the grid or absolutely:

```yaml
- cell: [row, column]      # icon on the left, text next to it
- at: [x, y]               # pixel coordinates
  size: [width, height]
```

| Type | Meaning |
|---|---|
| `tile` (default) | icon + text in one grid cell |
| `text` | text only |
| `icon` | icon only |
| `image` | PNG from `/homeassistant/aton_icons` |
| `rect` | filled area (`bg`) |
| `calendar` | calendar sheet with the day number (9×8) |
| `clock` | time HH:MM |
| `clock_wd` | time HH:MM plus a weekday bar |
| `notify` | [message line](#notifications) — empty until something is pending |
| `icons` | [a list of icons](#icon-lists) from a template, wrapped into the area |
| `series` | [columns](#column-series) of label / icon / label — an hourly forecast, for example |

Two keys apply to every type:

| Key | Meaning |
|---|---|
| `layer` | drawing order. Everything is on 0 and is drawn in list order — base image first, then the screen groups. A higher layer is drawn later and therefore on top |
| `visible_when` | Jinja condition. If it does not match, the tile is skipped. A broken condition draws the tile and reports the error — a tile missing because of a typo is looked for in the image |

Beyond these you can add your own types as Python files in `/config/aton_widgets` — they
bring their own keys and their own form in the configurator. See
[Custom widget types](custom-widgets.md).

### Text — exactly one source

```yaml
value: sensor.xy          # a state
attribute: temperature    # optional: an attribute instead of the state
format: "{:.1f}°C"        # Python format string
decimals: 2               # instead of format: round and drop zeros (12.30 → "12.3")
scale: 0.001              # multiply first
unavailable: "--"         # shown when the value is missing

text: "Fixed"             # or: fixed text
template: "{{ … }}"       # or: Jinja
```

### Icon — four forms

```yaml
icon: temp_o                       # a fixed name

icon:                              # from a state, exact match
  value: binary_sensor.rain
  map: {"off": dry, "on": wet}
  default: dry

icon:                              # from a number, threshold ≥
  value: sensor.battery
  steps: {100: batt_100, 50: batt_50, 0: batt_0}

icon:
  template: "{{ 'day' if is_state('sun.sun','above_horizon') else 'night' }}"
```

`color` understands the same four forms — that is how a field changes colour when
something needs attention.

⚠ `"off"` and `"on"` need the quotes; see [the configurator page](configurator.md#two-limits-worth-knowing).

### Moving the text field

```yaml
text_at: [41, 27]     # its own position instead of the grid one
text_width: 55        # wider than one grid column
align: left | center | right
```

### Icon lists

A row of icons whose *content* comes from a template — status symbols, active rooms,
whatever the state says:

```yaml
- type: icons
  at: [0, 18]
  size: [64, 18]
  spacing: 1              # pixels between two icons, horizontally and vertically
  align: left             # left | center | right
  template: >-
    {% for r in ['liv','kit','bat'] if is_state('binary_sensor.' ~ r ~ '_window', 'on') %}
      r_{{ r }}
    {% endfor %}
```

The names come from the **text source** — `template`, `value` or `text` — separated by
commas or whitespace. So everything text can do works here too, above all Jinja. A list
without a source is refused when loading; it could never show anything.

- **Wrapping is automatic.** Icons fill left to right and continue on the next row until
  the height is used up. What does not fit is dropped **and reported** — silently losing
  icons looks like "the template returns too little".
- **Columns line up.** All cells are the same size (the widest icon in the list, or
  `cell_size: [w, h]`), and each icon is centred inside its cell. Without that, one wider
  icon — `cal` is 9 px, the rest are 8 — would shift everything after it and the second
  row would sit askew under the first.
- **A typo costs one icon, not the tile.** An unknown name is skipped and named in the
  operations tab; with a list from a template that is the normal case, not an exception.

### Column series

Columns of *label, icon, label* — built for an hourly forecast, but not limited to it:

```yaml
- type: series
  at: [0, 40]
  size: [128, 22]
  spacing: 2
  align: center
  template: "14|sol_o|21, 15|wet|20, 16|wet|19, 17|dry|18, 18|dry|17"
```

Columns are separated by commas, the **rows** of a column by `|`. A part prefixed with
`@` is an icon, everything else is text — so the template decides the arrangement, not the
widget:

```
14|@w_sun|21°     text, icon, text (the hourly forecast)
Mo|Di             two rows of text
@w_sun|@w_rain    two rows of icons
@r_liv|22°        an icon above a label
@r_liv            a single icon
```

⚠ **Why the `@` and not "detect it automatically".** Without a marker the renderer would
have to guess whether `info` means the text or the icon of that name — and drawing a new
icon could then silently change an existing tile, because a former label suddenly passes
as an icon name.

Rows are the same height across all columns (the tallest occurrence per row), so mixed
columns share a baseline. A row nobody uses costs no height.

**Styling per row.** Colour and font are set on the tile, not in the template — the data
comes from Home Assistant and should not have to carry presentation:

```yaml
- type: series
  color: ffffff                          # the tile's default
  row_colors: [808080, "", ffcc00]       # hour grey, icon row untouched, temperature amber
  row_fonts: ["", "", spleen-5x8]        # a larger font for the last row
  template: "{{ state_attr('sensor.aton_forecast','series') }}"
```

The position in the list is the row. An empty entry — or no entry at all — means "as the
tile". Both spellings work: a YAML list as above, or a comma list (`808080, , ffcc00`) for
the configurator's form field, which has no list editor.

A row with a larger font gets more height, so nothing overlaps. An unknown font name costs
that row's styling, not the tile: it falls back to the tile's font and says so. A malformed
colour is refused when loading — at draw time it would throw on every frame without saying
where it stands.

**Why this exists instead of three tiles.** `text` + `icons` + `text` would work, but the
alignment then hangs on the template padding every label to the same width — and that
breaks the moment you change the number of columns or the area. Here the columns are flush
by construction: every cell is the same width (the widest content, or `cell_size`), and
each part is centred inside it. Wrapping, truncation and the "icon not found" report work
as they do for [icon lists](#icon-lists).

⚠ **Weather condition icons are not shipped.** The built-in set has `sol_i`, `sol_o`,
`dry`, `wet`, `lux` and the `wind_*` family — nothing for cloudy, showers, fog or storm.
Draw them in the *Icons* tab and map the condition to the name in Home Assistant, so the
name exists in exactly one place.

## Screen groups

An area whose content is exchanged. Each group becomes a selector
`Automatic | <screen> | …` in Home Assistant.

```yaml
screen_groups:
  - id: fields
    name: Fields
    region: [0, 36, 128, 18]        # x, y, width, height
    screens:
      - name: Solar
        when: "{{ states('sensor.pv') | float(0) > 0 }}"
        widgets: [...]
      - name: Temperatures
        when: always                # fallback when no condition matches
        widgets: [...]
```

- **Automatic**: the first screen whose `when` is true; otherwise the first without a
  condition.
- **Picking by hand** in HA beats `when`.
- A switch as a trigger is just a condition:
  `when: "{{ is_state('switch.solar_view', 'on') }}"`.
- Several groups side by side are fine — each gets its own selector.

### Pages — one screen, several versions

A screen may hold **pages** that take turns. In the selector the screen still appears
once; that is what separates pages from two screens, where picking one by hand would stop
the rotation.

```yaml
- name: Solar
  page_cycles: 2          # master switch, and the default per page
  pages:
    - name: Production
      cycles: 2              # stays twice as long as the other page
      widgets: [...]
    - name: Strings
      cycles: 1
      widgets: [...]
```

- `cycles: 0` (or omitted) means **as long as the screen says**.
- `page_cycles: 0` stops the rotation entirely — the first page only — **even if
  individual pages carry a number**. Otherwise the documented meaning would be true or
  false depending on what the pages happen to contain.
- One cycle is one `interval`. At `interval: 5`, two cycles are ten seconds.
- Which page is due is computed from the **clock**, not from a frame counter. A counter
  would be advanced by the configurator's preview as well, and two panels would drift
  apart over time.

## Notifications

A message line is a tile like any other — `type: notify`. It draws nothing while no
message is pending, and the text comes from the service call, not from the description:

```yaml
widgets:
  - type: notify
    at: [0, 18]
    size: [128, 8]
    layer: 1               # above the screen groups, see below
    visible_when: "{{ is_state('input_text.confirmed_room', 'Living room') }}"
    max_bar_chars: 30      # longer than that: WLED's own marquee
    levels:
      info:    {bg: 00c000, fg: ffffff}
      warning: {bg: c00000, fg: ffffff}
```

⚠ **`layer` matters.** Tiles are drawn in the order they appear — base image first, then
the screen groups. A message line on layer 0 that overlaps a group would be painted over
by it. `layer: 1` draws later and therefore on top. (The old `notify:` block always
behaved that way; its translation sets `layer: 1` for you.)

From an automation, through the companion integration's service:

```yaml
action: aton.notify
data:
  text: Washing machine done
  level: warning
  duration: 60
```

Clear with `aton.notify_clear`; without an `id` everything goes. With several panels the
field `panel` picks one — without it the call applies to all.

### Several lines: channels and level filters

Every message line without a `channel` is a **main line**. A line with a channel takes
only messages of that channel:

```yaml
widgets:
  - type: notify                 # main line
    at: [0, 18]
    size: [128, 8]
    layer: 1
  - type: notify                 # warnings only, own place, red
    at: [0, 54]
    size: [128, 8]
    layer: 1
    channel: warnings
    show_levels: warning
```

```yaml
action: aton.notify
data:
  text: Window open, it is freezing
  level: warning
  channel: warnings
```

- A message **without** a channel appears in every line without one.
- A message **with** a channel appears in the lines carrying it — and, if no line carries
  it at all, in the main line. A typo in `channel:` must not make the message vanish
  silently; the operations tab notes it as well.
- `show_levels` is a comma-separated list (`warning`, or `info, warning`). A level that
  the line's `levels:` does not define is refused when loading — such a line would stay
  empty forever.
- `aton.notify_clear` also takes `channel`: it then clears that channel only.
- ⚠ **Only one marquee at a time.** WLED scrolls in a single segment
  (`scroll_segment`), so only the first line whose text exceeds `max_bar_chars` scrolls.
  The second one says so instead of scrolling silently.

### The old `notify:` block

The per-panel block still works and is translated into the tile above while loading — no
description needs rewriting:

```yaml
notify:                    # equivalent to a `type: notify` tile with layer: 1
  region: [0, 18, 128, 8]
```

It has no channels, and its position lives in `region:` as numbers rather than being
draggable in the preview. The configurator offers **Convert to tile** on the notification
node for exactly that reason.

## Fonts

| Name | Origin |
|---|---|
| `5x3` | built in, a compact 3-pixel-wide font |
| `matrix5x3` | the same as a BDF file (`fonts_src/`), editable with a font editor |
| `spleen-5x8`, `spleen-6x12`, `spleen-8x16`, `spleen-12x24` | shipped |
| `ter-*` | Terminus, shipped |
| your own | `.pil`, `.bdf`, `.pcf`, `.ttf`, `.otf` in `/homeassistant/aton_fonts` |

Vector fonts need a size: `font: mine@8`. Rasterising is done **without** antialiasing —
a half-lit pixel is no gain on an LED matrix.

## Your own icons

47 icons are built in (`info`, `temp_i`, `wind_nw`, `power_battery_50` …); the icon grid
in the configurator shows them all.

### The icon editor

Tab **Icons**. On the left the list — a click opens an icon for editing, including a
shipped one. On the right the canvas.

| | |
|---|---|
| **Pen / eraser / pipette** | draw, erase (opacity 0), pick a colour from a pixel |
| **Fill all / clear all**, **Undo** | up to 40 steps back |
| **Palette, colour picker, hex** | 20 saturated colours plus free choice |
| **Opacity** | 0 to 255, separate from the colour |
| **Size** | 8×8, 8×16, 16×16, 9×8, 32×8 — what you drew is kept as far as it fits |

⚠ **Why opacity and black are two different things:** in the shipped icons black is
transparent, and a black area cannot be drawn there at all. Your own file has a real alpha
channel and can do both. That is why the eraser (opacity 0) is separate from the colour
black; transparent pixels are shown as a chequerboard so the two are not confused.

Saved as PNG in `/config/aton_icons`. A running display picks it up **immediately** — no
reload, no restart.

Saving under the name of a shipped icon **overrides** it. Deleting frees it again; only
your own files can be deleted.

### By hand

1. Create the folder **`/config/aton_icons`**.
2. Put a file in it: **`.png`**, `.gif` or `.bmp`. The **file name without the extension
   is the icon name** — `my_icon.png` is used as `icon: my_icon`.
3. Press **Reload** in the configurator (or restart the app).

Size: **8×8** fits the icon column of a grid tile; for `type: image` any size is allowed
and the image is not scaled. Transparency comes from the file's **alpha channel** —
unlike the built-in icons, where black is transparent. So if you want an area to really be
black, you need a PNG with alpha.

## Templates (Jinja)

Evaluated against the app's own state mirror, so without asking HA each time. Available
are `states`, `state_attr`, `is_state`, `is_state_attr`, `has_value`, `now`, `utcnow` and
the Jinja filters (`float`, `int`, `default`, `round`, …).

⚠ **This is a subset of Home Assistant's template language.** Device resolution, `expand`,
`area_*` and history data are missing. If you need those, build a template sensor in HA
and read that here.

⚠ The most common mistake: `states('sensor.x') | round(0)` raises when the entity is
missing or unavailable, because `states()` then returns the string `unknown`. Filter
first: `| float(0) | round(0)`.

## What appears in Home Assistant

The app itself creates **no** entities — the companion integration does
(`custom_components/aton`, installable through HACS). It talks to the app over its HTTP
API inside the internal Docker network; **no MQTT broker** is involved.

Per panel you get **one device** with:

| Entity | |
|---|---|
| `select` per screen group | `Automatic \| <screen> \| …` |
| `sensor` per group | what is actually being shown |
| `image` | preview of the frame, can go on a dashboard |
| `binary_sensor` | reachable, drawing |
| `sensor` | frames, changed pixels, bytes per frame, send errors, last error |
| `button` | send full frame |
| `number` | brightness (only without `brightness.entity`) |

Plus the services `aton.notify` and `aton.notify_clear`.

Without the integration the app keeps running — matrix, screens and automatic switching
work; you operate it from the app's own page in the sidebar.
