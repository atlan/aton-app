# Custom widget types

The built-in types cover what can be *described*: a tile, a text, an icon, a clock. What
they cannot cover is anything that **computes** — a bar, a ring, a needle, your own way of
turning a number into pixels. For those, you bring the type yourself: a Python file in
`/config/aton_widgets`, and `type: your_name` in the YAML.

A custom type is not a second-class citizen. It declares its own fields, and from that one
declaration Aton derives both the validation when the description is loaded and the input
form in the configurator. A typo in one of your own keys is reported the same way a typo in
`value` is.

## Turning it on

⚠ This runs Python that Aton did not ship, inside the add-on container. It is therefore
**off by default** — unlike `aton_icons` and `aton_fonts`, which only ever read data.

In the add-on configuration:

```yaml
custom_widgets: true
```

With the switch off the directory is not read at all, and `type: bargraph` fails to load
with a note pointing at this option — so you are never left guessing whether the file was
found and rejected or never opened.

## The smallest plugin that works

`/config/aton_widgets/dot.py`:

```python
from aton_api import Feld, widget


@widget("dot", felder=[
    Feld("sensor", "entitaet", "Sensor", pflicht=True),
])
def zeichne(bild, w, ctx):
    farbe = "30c030" if ctx.state(w.optionen["sensor"]) == "on" else "802020"
    ctx.zeichner(bild).rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1],
                                 fill=ctx.rgb(farbe))
```

```yaml
- type: dot
  at: [30, 0]
  size: [2, 2]
  sensor: binary_sensor.window_open
```

Import from **`aton_api`**, not from `panel.plugin`. The package name is internal — the app
runs as `panel` in the container and lives under `aton/panel` in the source tree — and
`aton_api` is the name that stays put.

A ready-to-copy example with more in it (fill level, colours, range) ships as
[`examples/widgets/bargraph.py`](../examples/widgets/bargraph.py).

## Declaring fields

`Feld(name, art, label, hilfe="", pflicht=False, vorgabe=None, optionen=[], min=None, max=None, einheit="")`

Allowed `art` values: `text`, `int`, `float`, `bool`, `farbe`, `entitaet`, `schrift`,
`symbol`, `vorlage`, `format`, `auswahl` (`auswahl` needs `optionen=[...]`).

Two rules the loader enforces, both at load time with the file name in the message:

- **A field may not be named like a built-in widget key** — `color`, `font`, `value`,
  `text`, `align` and so on. `_widget` in the loader consumes those itself, so the value
  would never reach your code. Name it `bar_color`, not `color`.
- **Composite kinds are not available** (`punkt`, `groesse`, `rechteck`, `textquelle`,
  `symbolquelle`, `farbquelle`). They carry their own conversions in the loader. If you
  need a position, take two `int` fields.

The checked values arrive in `w.optionen`, keyed by field name. A field with a `vorgabe`
is always present; an optional field without one is absent, so use `w.optionen.get(...)`.

### `entitaet` fields do more than look nice

★ Aton subscribes in Home Assistant exactly to the entities a description mentions. Those
come from the `entitaet` fields — a sensor your plugin reads through some other route
(a hard-coded ID, a string you assemble) is **not** subscribed, and the widget then never
redraws. It does not fail; it just quietly stands still. Declare what you read.

## What your function receives

`zeichne(bild, w, ctx)`

| | |
|---|---|
| `bild` | the panel image, PIL `RGBA`. Draw in absolute coordinates |
| `w.x`, `w.y`, `w.w`, `w.h` | position and size of your widget |
| `w.optionen` | your checked field values |
| `w.bg` | already painted for you before your function runs |

`ctx` is the whole interface to the renderer — deliberately narrow, so that internal
renames cannot break files that live outside this repository:

| Call | Gives you |
|---|---|
| `ctx.state(eid)` | the state as a string, or `None` |
| `ctx.attr(eid, name)` | an attribute |
| `ctx.zahl(eid, attribut=None)` | the state as a float — `None` for `unknown`, `unavailable` and anything unparseable |
| `ctx.vorlage(text)` | render a Jinja2 template, as `template:` does |
| `ctx.rgb("ff8800")` | hex to an `(r, g, b)` tuple |
| `ctx.zeichner(bild)` | PIL `ImageDraw` — points, lines, rectangles |
| `ctx.schreibe(bild, text, x, y, breite, hoehe, farbe, schrift, align)` | text in a field, clipped |
| `ctx.symbol(bild, name, x, y)` | an icon from `aton_icons` or a built-in one |
| `ctx.schrift(name=None)` | a font with `.measure(text)` and `.draw(draw, (x, y), text, rgb)` |
| `ctx.panel` | the panel config (size, id, grid) |

## When something breaks

- **The file does not import** (syntax error, missing name, a field that collides with a
  built-in key): the type is not registered, the message names the file, and every *other*
  plugin still loads. The app starts.
- **The drawing function raises**: that one tile stays empty for that frame, the message
  names the plugin **and its file**, and the rest of the picture is drawn. Nothing stops.

Both kinds show up in the add-on log; load errors also travel to the configurator.

## Reloading

**Re-read** in the configurator's toolbar picks up a new or changed plugin file without
restarting the add-on — the same step that notices new files in `aton_icons` and changed
`fonts:` rules. It refreshes both halves: the server re-scans the directory, and the page
then re-fetches the type list, which it would otherwise hold from when it was opened.

⚠ Re-reading rebuilds the panels, so a manual screen selection and any running
notification reset. Unsaved edits in the configurator are discarded — it asks first.

Saving the description does the server half too, so a plugin added before a save is picked
up as well; only the type list in an already-open page then still needs a page reload.

Files starting with `_` are skipped, so helper modules of your own are safe from being
scanned for widget types.
