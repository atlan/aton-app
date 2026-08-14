# Changelog

## 0.21.1 — several scrolling texts at once

Until now the rule was "there is only ONE scroll segment per device", and a second running
message got a refusal. **That was Aton's limit, not WLED's.** Checked against the WLED-MM
source:

- `FX.h`: `#define SEGENV strip._segments[strip.getCurrSegmentId()]` — scroll offset
  (`aux0`), colour shift (`aux1`) and timing (`step`) live **in the segment itself**. Two
  segments running "Scrolling Text" are therefore independent.
- `FX_fcn.cpp`: `service()` walks `_segments` in **index order** — a higher index is
  serviced later and sits on top where they overlap. The notification row has always
  relied on exactly that.
- `MAX_NUM_SEGMENTS` is **32** on ESP32 (16 only on ESP8266).

Every notification row now gets its own segment, assigned **at load time** and not per
message. That is the heart of it: the assignment has to be stable. If row 2 took row 1's
segment whenever row 1 fell silent, WLED would restart the running animation — the offset
belongs to the segment. In the renderer the order would depend on the currently active
screen, which is precisely not stable.

- `clear_segments_to` now cleans up above the **highest** scroll segment, not above the
  first — otherwise every full frame would have deleted the second scrolling text.
- If the number of rows does not fit below `clear_segments_to`, **loading** fails with the
  path and the arithmetic, instead of overwriting a segment at runtime.
- The signature that prevents a needless re-send now applies **per segment**.

⚠ **Side finding in the WLED source:** `WLED_MAX_SEGNAME_LEN` is 48 (ESP32) or 32
(ESP8266) — Aton's `max_chars` defaults to **60**. A long message was therefore truncated
by the device with nothing said anywhere. It is now visibly shortened to 32 (the smaller
of the two limits, so it never surprises on any device).

## 0.21.0 — three new widget types, and the app looks back for the first time

Asked which widgets were missing, the installation's own YAML gave the answer.

**`sparkline` — the history of an entity.** Until now *everything* on the panel was "now";
`panel/` contained no `history`, no `recorder`, no `statistics`. That left out the very
genre a dot matrix is made for: the curve.

- The data comes from HA's recorder over the existing WebSocket. For that the connection
  can now **ask** at all instead of only sending (`hass.frage`) — pending requests with a
  timeout, and on a dropped connection the waiters are woken instead of being left to run
  into it.
- A **background store** (`panel/verlauf.py`) keeps the curves fresh, every five minutes.
  `Renderer.frame()` is synchronous and runs 720 times an hour — a recorder query has no
  business in that loop.
- Reduction to 256 points is done by **averaging, not sampling**: taking every n-th value
  would drop exactly the peak you wanted to see.
- Without data **nothing** is drawn and the reason is reported. A line along the baseline
  would look like "the value was zero all along".
- Without `scale_min`/`scale_max` the range of the data applies. With a fixed 0 an outdoor
  temperature around 20 °C would be a flat line at the very top.

**`bar` — built in instead of an example.** It only existed as a 52-line plugin
(`examples/widgets/bargraph.py`), which requires `custom_widgets: true` — an option that is
off for good reason, because that directory executes code. Battery, cistern, self-
sufficiency are too common for that price. The colour comes from the ordinary colour
source, so `steps:` shades the bar by threshold without the type needing anything of its
own.

⚠ The keys are **`scale_min`/`scale_max`**, not `min`/`max`. Those are exactly what the
example plugin uses, and a plugin field occupied by a built-in key is rejected on load
(since 0.13.0, deliberately). The built-in types would otherwise have broken every foreign
file that uses `min:`. **The tests caught this**, not me.

**`lines` — several text rows from one source.** `series` makes columns, `icons` makes
icons; text rows did not exist. Anyone wanting a list built one widget per row with a
hand-computed `at:` — inserting a row shifted everything. A leading `@name ` is an icon,
the same notation as in `series`. Rows that are too long are **shortened, not wrapped**:
wrapping would turn three tasks into one.

## 0.20.2 — the brightness slider works, and the page stops jumping

Two separate bugs that together looked like one: "move the slider, nothing happens, then
the page jumps to the top, and the matrix stays just as bright — only *Send full frame*
does anything."

**1. A brightness change now forces a full frame.** On a frozen segment the segment
brightness only takes effect once the pixels are *written again*; the value alone does not
change a standing image. On a panel whose content moves constantly this never shows — on a
static one it shows completely. Six cycles measured:

| Panel | changed pixels per cycle |
| --- | --- |
| Living room side matrix (clock, temperatures) | 18–43 |
| Living room TV matrix (to-do list) | **0 in 5 of 6** |
| Entry matrix | **0 in 6 of 6** |

That is why only the button that does exactly this helped. Now the app does it by itself.
Price: 34 kB instead of 40 bytes, but only when someone touches the slider.

**2. The Operations view re-attached every card on every poll.** `appendChild` on an
already-attached node detaches it and puts it back — at a 3 s poll that is 20 times per
minute per card. Recorded in the browser with a MutationObserver:

    12:40:13  gone p-living_room · new p-living_room · gone p-entry · new p-entry · …
    12:40:16  same
    12:40:19  same

That takes focus away from the control and makes the page jump — the slider was pulled out
from under the user's finger. Only cards that are actually in the wrong place are moved
now; ordering by the config file stays.

## 0.20.1 — the wait belongs on the panel

The 90 seconds from 0.20.0 were chosen from **two** measurements (17.9 and 20.3 s). While
verifying on the same day the same panel took **95 s** — a switch script with a fixed 20 s
delay, after which HA sets up the config entry.

New: **`gate.wartezeit`** per panel, default 90 s. A value that is too low costs one
attempt and then the back-off, not a broken display — but whoever knows their device should
be able to set it instead of hunting for it in the source.

## 0.20.0 — nothing is sent until someone is there

Aton used to send as soon as the panel was *switched on* — not as soon as the device
*answers*. Those are two different things, and measured on the installation on 2026-08-14
there are 18–20 seconds between them:

| Panel | power (`switch.…`) | gate (`light.…_power`) | gap |
| --- | --- | --- | --- |
| Living room side matrix | 11:21:18.33 | 11:21:38.59 | **20.3 s** |
| Living room TV matrix | 10:43:20.08 | 10:43:38.01 | **17.9 s** |

A full frame went out into that gap — in eight blocks, each of which ran into its own
timeout. **Eight send errors per power-on, for one single fact.** And a matrix that spent a
night without power racked up **5888**.

Four changes:

- **Wait for the gate, not for the power.** Home Assistant only sets the gate entity to
  `on` once it is talking to the device — so the reachability check had been there all
  along, `gate.fallback` just overtook it. The fallback was meant as an emergency exit
  (chicken-and-egg without a second segment), not as an accelerator. It now applies only
  after **90 seconds**, and the attempt that follows counts as a probe.
- **After the first failed block, stop.** The first block answers the question completely;
  a dedicated ping would be redundant and would prove less.
- **Back-off** after a failed attempt: 10, 20, 40, 60 s. Rendering continues on the normal
  cycle so the preview does not freeze — only sending is skipped.
- **Reachability is a state**, not an event: the Operations view shows "not reachable since
  02:41" instead of thousands of incidents. Only failures that happen **while** HA
  considers the device reachable are counted.

Plus an explicit `ClientTimeout` — without it aiohttp's default of five minutes applied.

**Also:** the preview of a panel that had never run since the app started was recomputed on
*every* request — the Operations view polls every 3 s, and because the clock and live values
are in the image, the preview of a switched-off matrix kept changing merrily. It is now
computed once and kept.

## 0.19.2 — the message after saving names the places

0.19.0 reported nothing after saving: what was counted was what had to be renamed in the
**draft** — and that came back from loading already migrated. What is counted now is what
changes in the **file**.

## 0.19.1 — the save button for renaming

Follow-up to 0.19.0, noticed during live testing: the hint "will be rewritten on save" was
there, but the **save button was disabled** — it depends on "unsaved changes", and right
after loading there were none. So the rename was only written when something else happened
to be changed.

A migrated config now counts as an unsaved change — which is what it is: the data model
differs from the file.

## 0.19.0 — the configurator rewrites outdated names

Until now Aton merely **tolerated** outdated names: `seiten`, `zyklen`, `wechsel_zyklen`,
`wechsel_s` and `type: serie` were accepted on load and stayed in the file. That got
expensive once: a widget with `type: serie` got no `row_*` fields in the configurator — the
form showed the new type, the file said the old one.

Now the configurator rewrites them, on save, and names every place — when opening the file
("will be rewritten on save") and afterwards.

- Renaming happens **in place**: the key keeps its position and its comment. `wechsel_s`
  (seconds) is converted to cycles using the same frame interval as the loader — after
  saving the panel behaves exactly as before.
- Writing happens **only on save**. Anyone maintaining the file by hand and not using the
  configurator notices nothing; the loader keeps accepting the old names.
- What cannot be converted (`wechsel_s: soon`) stays and does not block saving — the
  complaint arrives on load as before.

## 0.18.0 — colour and font per row

`series` can now style every row individually:

```yaml
- type: series
  color: ffffff
  row_colors: [808080, "", ffcc00]     # hour grey, icon row untouched, temperature amber
  row_fonts: ["", "", spleen-5x8]      # last row larger
```

**The position in the list is the row**; an empty entry — or none at all — means "same as
the widget". Both notations work: a YAML list or a comma list (`808080, , ffcc00`), because
the configurator's form has no field type for lists.

**The style lives on the widget, not in the template.** The data comes from Home Assistant
and should not carry presentation along — otherwise a sensor would have to know which
colour looks good on which matrix.

- A row with a larger font gets **more height** so nothing overlaps.
- An unknown font costs only that row's style, not the widget: it falls back to the widget's
  font, with a message.
- A malformed colour is rejected **on load**, with the place in the file. Otherwise drawing
  would throw an exception every frame without saying where.

## 0.17.1 — the rename hint was too chatty

The message "`seiten` is now `pages`" printed the value it had taken over — and that is the
complete page list with all widgets. The log then held a screenful of YAML in which the
actual message drowned. Now only hinted at: "11 entries" for lists, otherwise the first
60 characters.

## 0.17.0 — English keys, and `series` describes its own layout

**The last German keys are gone.** The rest of the config language had long been English
(`type`, `at`, `size`, `template`, `align`, `spacing`); four stragglers remained:

| old | new |
|---|---|
| `type: serie` | `type: series` |
| `seiten:` | `pages:` |
| `zyklen:` | `cycles:` |
| `wechsel_zyklen:` | `page_cycles:` |

⚠ **The old names remain valid** — through the same mechanism that already catches
`wechsel_s`. Your config does not have to be touched; the log carries a hint, and the next
save in the configurator rewrites it.

**`series` now decides the layout in the template.** Previously three rows were fixed: text,
icon, text. Now there can be any number, and `@` marks an icon:

```
14|@w_sun|21°     text, icon, text (the hourly forecast)
Mo|Tu             two text rows
@w_sun|@w_rain    two icon rows
@r_liv|22°        icon above a label
@r_liv            icon only
```

⚠ **Why `@` and not automatic detection:** without a marker the renderer would have to guess
whether `info` is the text "info" or the icon `info` — and a newly drawn icon would silently
change existing widgets, because a text that worked yesterday suddenly passes as an icon
name.

Rows are equally tall across all columns (the tallest occurrence per row) so mixed columns
sit on one baseline. A missing icon keeps its place instead of shifting the neighbouring
columns.

## 0.16.2 — horizontal and vertical spacing separated

`spacing` applied to both axes. That does not work out: columns need air, the three rows of
a column belong close together — with a single shared value one of them is always wrong.

New is **`line_spacing`** for the vertical direction (in `series` between label, icon and
label; in `icons` between wrapped lines). Left empty, `spacing` still applies to both —
existing widgets do not change.

```yaml
- type: series
  spacing: 4          # air between the columns
  line_spacing: 0     # rows flush
```

Noticed by the user on the image, not by me.

## 0.16.1 — uneven line spacing in type `series`

Above the icon there was 1 px too little, below it 1 px too much — at `spacing: 2` measured
1 and 3 px instead of 2 and 2. Cause: `_schreibe` indents its text 1 px down within the
field; that was not accounted for in the arithmetic.

The labels are now placed exactly that one pixel higher. Re-measured: `spacing: 2` → 2/2,
`spacing: 1` → 1/1, `spacing: 0` → flush. A test pins all four cases.

⚠ This showed up on the rendered image, not in the seven tests — those checked THAT there
are three rows, not in what rhythm.

## 0.16.0 — columns of label, icon and label

New type **`series`**, built for an hourly forecast:

```yaml
- type: series
  at: [0, 40]
  size: [128, 22]
  spacing: 2
  align: center
  template: "14|sol_o|21, 15|wet|20, 16|wet|19, 17|dry|18, 18|dry|17"
```

Columns separated by comma, the three parts of a column by `|`. Every part may be empty
(`|rain|` is just an icon, `14||21` just numbers), and a row nobody uses costs no height.

**Why a dedicated type and not three widgets:** `text` + `icons` + `text` would also do it,
but the alignment would depend on the template padding every label to the same width — and
that breaks as soon as you change the number of columns or the area. Here the columns are
aligned by construction: equally wide cells, each part centred inside. Wrapping, the
truncation message and the hint about unknown icons work as in type `icons`.

⚠ **Aton does not ship weather icons.** The built-in set has `sol_i`, `sol_o`, `dry`, `wet`,
`lux` and the `wind_*` family — nothing for cloudy, showers, fog, thunderstorm. Draw those
in the icon editor; the mapping weather state → icon name belongs in Home Assistant so that
the name lives in exactly one place.

## 0.15.0 — icon lists from a template

New widget type **`icons`**: a list of icons in a defined area whose content comes from
Jinja.

```yaml
- type: icons
  at: [0, 18]
  size: [64, 18]
  spacing: 1
  template: >-
    {% for r in ['liv','kit','bat'] if is_state('binary_sensor.' ~ r ~ '_window','on') %}
      r_{{ r }}
    {% endfor %}
```

The names come from the **text source** (`template`, `value` or `text`), separated by comma
or space. That way the type needs no key of its own and can do everything text can do.
Without a source it is rejected on load — it could never show anything.

**Wrapping is automatic:** the icons fill left to right and continue on the next line until
the height is used up.

**The columns line up.** All cells are the same size (the widest icon in the list, or
`cell_size: [w, h]`), each icon centred within. Without that a wider icon — `cal` is 9 px,
all others 8 — would shift everything after it, and the second line would sit crooked under
the first.

**A typo costs one icon, not the widget.** An unknown name is skipped and named in the
Operations tab; with a list coming from a template that is the normal case, not the
exception. What does not fit into the area is reported too — silently dropping it would look
like "the template delivers too little".

Nine tests pin this down, including the flush lines with mixed widths.

## 0.14.2 — the warning stayed invisible despite 0.14.1

0.14.1 attached it to the preview and cleared it after showing. Overlooked: `waehle()`
triggers its **own** preview on a screen change, which returns earlier — it showed the
warning, cleared it, and the second refresh 350 ms later restored the default text. Flashed
up and gone before anyone could read it.

Now it stays until something else is selected.

## 0.14.1 — the warning when moving was gone after 350 ms

The check from 0.14.0 ran correctly, you just could not see its result: `kachelVerschieben`
wrote the hint into the line immediately, and `nachAenderung` fetches the preview 350 ms
later — which resets the hint line to its default text.

Noticed while checking in the browser: a widget moved into the "Solar" screen (region
`[0, 26, 128, 27]`), it sits there at y = 9 — far outside — and the line still showed the
usual text.

The warning now travels as `K.umzugHinweis` and is set **when the new image is up**; after
that it is cleared. It applies to exactly one refresh.

## 0.14.0 — widgets can be moved into another list

↑/↓ only made progress **within** one list. Getting a widget out of the base image into a
screen group — or onto the second matrix — was only possible through the YAML editor.

Now a widget's toolbar carries a dropdown **"Move to …"** with all targets: the base image
of every panel and every page of every screen, labelled with the full path
(`Living room matrix › Fields › Solar › Page 2`) — with screens of the same name in two
panels there is otherwise no telling which is meant. If the target has no `widgets:` list,
it is created.

**The coordinates stay unchanged** — even when moving between two panels with different
grids. Converting would be well meant and surprising: the widget would end up somewhere
other than where you put it. Instead it is checked and stated:

- outside the **panel area** → will not be drawn at all
- outside the **region of the screen group** → will be drawn, but not swapped out on a
  screen change

The move happens in both cases anyway; the hint sits under the preview, and the preview
shows immediately where the widget landed.

No drag & drop in the tree: dragging across a long structure is hard to hit on a tablet, and
invalid targets would have to be marked specially. The dropdown only knows valid ones.

## 0.13.3 — collapsing works now, parents included

0.13.2 fell short. The path to the selection was still expanded on **every** redraw — I had
only exempted the selected node itself. Everything above it stayed pinned: a panel could not
be closed as long as anything inside it was selected. Reported exactly like that and
measured in the browser — `panels/0` was still in `K.offen` after clicking the arrow.

Expanding is a consequence of **selecting**, not a state of drawing. The path is now opened
once in `waehle()`, and `baumZeichnen` expands nothing at all any more.

## 0.13.2 — tree nodes could not be collapsed

Expanding worked, collapsing did not: the arrow jumped straight back to ▾.

The tree expands the path to the selection — up to and **including the selected node**. But
clicking the label selects the node, so its own key was re-entered on every redraw:
`K.offen.delete(…)` took effect, and three lines later the loop undid it.

Measured in the browser — after clicking the arrow the key was unchanged in `K.offen`,
arrow ▾, children visible:

    after clicking "Base image":  offen = [… "panels/0/widgets" …]
    after clicking the arrow   :  offen = [… "panels/0/widgets"]

Drawing now only expands the **parents**. That a selected node opens itself remains — it
happens once on the click (`waehle`) instead of on every draw.

⚠ The bug is old: the loop has been like that since the rename to Aton (0.8.0) and has
nothing to do with the notification row.

## 0.13.1 — the frames in the preview now correct themselves

The clickable frames sit at `bild.clientWidth / bild.naturalWidth`. If that width is not
settled at draw time (image not laid out yet, tab hidden), the fallback `skala = 1` applies —
and then every frame is off by the same **factor**. Not a fixed offset: they drift further
the further right and down they sit.

Until now this was only corrected by the next window event. Reported on 2026-08-08: the
frames sat wrong and only snapped into place when the window was resized. Waiting for an
event that has nothing to do with the matter is the wrong condition.

Now a `ResizeObserver` watches the image itself and re-places the frames as soon as it gets
its size — and only then, otherwise redrawing would trigger the observer again.

⚠ The cause is therefore **not proven**, only the condition repaired: the state from back
then could no longer be measured. The pattern argues for this factor error (drift grows with
distance from the origin), and the place depended on a foreign event anyway.

## 0.13.0 — the notification row is a widget

It was the last special case: a block of its own per panel, with `region:` in numbers
instead of a position you can grab, drawn along its own path after everything else. Now it
is a widget like any other:

```yaml
widgets:
  - type: notify
    at: [0, 45]
    size: [128, 8]
    layer: 1
```

That makes it movable in the preview, clickable and duplicable — and there can be several.

**Channels and level filters.** A row with `channel: warnings` only takes messages of that
channel (`aton.notify` gained a field for it), `show_levels: warning` narrows it to one
level. A row without a channel is the main row — it shows everything channel-less **and**
messages whose channel has no row at all. A typo in the channel must not swallow the message
without trace; the Operations tab carries a line about it.

Two messages can now stand at the same time. Previously the app picked one and the second
was invisible — with only one row that was right, with two it would be a bug.

**`layer:` on every widget.** Drawing follows list order, first the base image, then the
screen groups. A notification row in the base image would therefore sit under an overlapping
group. Whoever is higher is drawn later and lies on top. Without the key nothing changes:
everything is at 0, and at equal layers the previous order holds.

**`visible_when:` on every widget.** Previously only the notification row could do this. A
faulty condition draws the widget anyway and reports the error — a widget missing because of
a typo is otherwise hunted for in the image.

**The old block stays valid.** `notify: {region: [...]}` is translated into exactly such a
widget on load, including `layer: 1` — no config has to be rewritten. In the configurator the
block carries a button **Convert to widget**; afterwards the row can be moved with the mouse.
The node "Notification row" only appears as long as the block is in the file.

⚠ **Only one scrolling text at a time.** WLED has a single scroll segment
(`scroll_segment`). If a message is already running, the second row says so instead of
silently doing nothing.

⚠ **For custom widget types:** the new keys (`layer`, `visible_when`, `channel`,
`show_levels`, `max_chars`, `max_bar_chars`, `levels`, `scroll_*`) are now taken by the
built-in schema. A plugin with a field of the same name is rejected on load — with file name
and reason, as before.

By the way: the form only shows type-bound fields for the matching type. `Image file` used to
appear on a clock as well; with the eight notification fields the form of every widget would
have become unusably long. Only the display is filtered — validation stays a flat key set,
otherwise every type change would be a dead end again (see 0.12.5).

## 0.12.6 — a set icon was a one-way street

In the icon field every click set a name; an empty state did not exist in the grid. Whoever
had once chosen an icon — or inherited it from the scaffold of a new widget — could only get
`icon:` out again in the YAML editor.

This became visible with types that draw no icon at all (`clock_wd`, `calendar`): there the
`icon:` and `text:` of the previous type stayed in the file as ballast, without effect on the
image — the structure tree then showed `"clock_wd"` in quotes, because the tree shows the
`text:` as soon as there is one.

Now the first cell in the grid is "no icon"; it deletes the key.

Second, the icon/colour field only read its value when the form was built. Changing the form
(fixed / map / steps / template) deletes the entry — after which the grid still showed an
icon as active that was no longer in the file at all. The value is now read fresh on every
draw.

## 0.12.5 — changing the type was a dead end

Anyone who set a widget to a custom type, filled in its fields and then switched to another
type got the whole config rejected:

    unknown keys: sensor — allowed are: align, at, attribute, …

The message was correct and still did not help: you never wrote `sensor` by hand, and in the
form the field had disappeared with the old type. Only the YAML editor led out.

Now the configurator clears the old type's keys along with the change. What the new type also
knows stays — two plugins may share a `sensor`.

And for hand-edited files the message says where the key came from:

    unknown keys: sensor — sensor belongs to type: bargraph. When changing the type the
    keys of the old one remain; delete them here — allowed are …

A genuine typo stays a plain message without this addition; otherwise it would be noise. Two
tests pin both down.

## 0.12.4 — the error message now sits where you are looking

0.12.3 made the message appear — but it stood **below** the stage, and with a tall panel
(64×128) the preview column is taller than the window. Displayed and yet off-screen: from
the user's point of view, still nothing.

The message now sits **above** the stage, directly under the heading — hidden it takes no
space, so it costs nothing. In addition it scrolls itself into view when it goes from
invisible to visible, but only then: scrolling on every keystroke would make the page
restless.

⚠ Lesson: `display !== 'none'` is not "the user can see it".

## 0.12.3 — rejected drafts finally say why

When the loader rejected a draft, the preview silently kept the old image. The reason was
computed and written into the message field — but its `display` stayed at `none`, because the
error branch was the only one that never set it. On screen it looked as if nothing happened
at all.

Noticed with a custom widget type missing its required field: "bargraph selected, nothing
changes in the preview". In the DOM
`panels[2].widgets[0].sensor: missing — type: bargraph needs it` had been there the whole
time.

⚠ The bug has been in since the rename to Aton (0.8.0) and affects **every** rejected config,
not just custom types.

## 0.12.2 — custom type was in the schema but not in the dropdown

0.12.0 extended `widget_typen` with the custom types — the list was right, the select field
still showed the built-in ones. Reason: the UI builds a `select` field from the `optionen`
**of the field** (`feldBauen` in konfigurator.js), and `optionen` of the `type` field still
pointed at the unchanged `WIDGET_TYPEN`.

So the custom type existed in the schema, was loaded according to the log — and was not
selectable in the configurator. From the outside that looked like a cache, and you go looking
in the wrong place.

A test pins both: the type is in the dropdown, and the built-in module list does not grow in
the process (an `append` on it would accumulate across all calls).

## 0.12.1 — "Reload" in the configurator

A file freshly placed in `/config/aton_widgets` could only be picked up by **restarting the
app**. On the server side the registries are otherwise only re-read at startup and when
saving the config — and even then the new type stayed invisible, because the page holds on to
its type list from the moment it was built.

The **Reload** button does both: first the server re-reads config, fonts, icons and custom
widget types, then the page fetches its schema again. 0.12.0 brought the mechanism but no way
to use it — the endpoint `/api/reload` existed and had not a single caller.

⚠ Reloading rebuilds the panels: manual selection and running messages are reset. Unsaved
changes in the configurator are lost — you are asked first.

## 0.12.0 — custom widget types, and the clock without the weekday bar

**Custom types.** Python files in `/config/aton_widgets` bring new widget types along. A file
registers not just a draw function but **its fields** — and from that same declaration the
load-time validation takes its allowed keys and the configurator its input form. A typo in a
custom key is therefore reported and not swallowed.

```python
from aton_api import Feld, widget

@widget("dot", felder=[Feld("sensor", "entitaet", "Sensor", pflicht=True)])
def zeichne(bild, w, ctx):
    ...
```

⚠ The new app option **`custom_widgets` is off by default**. `aton_fonts` and `aton_icons`
read data — this directory executes code, and that must not happen just because someone drops
a file in. If it is `false` the folder is not even read, and an unknown type in the config
says exactly that.

★ Fields of kind `entitaet` are not just labels: the subscriptions to Home Assistant are
built from them. A sensor that a plugin reads some other way is not subscribed — the widget
then never redraws and does not look broken while doing it.

Errors never cost more than their own place: a file that cannot be imported does not stop the
others; an exception while drawing costs its widget for that frame. The message names the
**file**, not just the place in the YAML.

**`clock` now exists twice.** `clock` draws only HH:MM, the weekday bar lives in `clock_wd`.

⚠ **Not backwards compatible:** every existing `type: clock` loses the bar, without an error
message. Whoever wants to keep it writes `clock_wd`. The bundled examples have been updated.

## 0.11.8 — the app now says which version it is

`/api/panels` additionally delivers `version`. The companion integration writes it into the
device as `sw_version` — so the device page states which version of the app is currently
driving the panel, instead of nothing.

⚠ **There were two version statements.** `panel/__init__.py` had always carried
`__version__ = "0.1.0"` while the app was at 0.11.7. Nobody read it, which is why it never
showed up — that is exactly how a duplicate survives. There is now only `const.version()`,
which reads `config.yaml`, i.e. the file the supervisor reads too. Three tests pin this down,
one of them explicitly checking that `panel.__version__` does **not** come back.

Along the way the device card was tidied: `model` is now `LED matrix 128×64` instead of
`128x64`, and the manufacturer is **WLED**, the counterpart — previously it said "Aton" and
duplicated the line HA sets for the integration anyway.

## 0.11.7 — the zoom now follows the column width

0.11.6 adapted the frames to the scaled-down image — correct, but the pixel graphics stayed
soft. Now the zoom is determined from the column width **before** the request, so the server
renders the image at the right size straight away.

Measured on the same page:

| Window | Column | Zoom | Image | Factor |
|---|---|---|---|---|
| 1720 | 1080 | 8 | 1024 px | **1.0** |
| 1200 | 560 | 4 | 512 px | **1.0** |

An integer zoom means sharp LED dots; previously the factor was an odd 0.931 and smeared
them.

⚠⚠ **Compute from the column width, never from the zoom reported back.** Writing
`K.zoomWunsch = p.zoom` builds a feedback loop: with `led_pitch` set, the zoom used differs
from the one requested, and the image then shrinks further on every pass (6 → 5 → 4 …). The
column is `minmax(320px, 1fr)` and does not depend on the image — so nothing goes in circles.

`max-width: 100%` and the factor from 0.11.6 remain as a net: with `led_pitch` above P3 the
server may use a larger zoom than requested.

## 0.11.5/0.11.6 — the widget frames stuck out of the preview

Noticed by the user on a screenshot: "the field frames stick out beyond the preview". Not a
display glitch of the image but a real bug in the UI.

★ **Two scales that did not match.** `.k-buehne img` has `max-width: 100%` — as soon as the
middle column is narrower than matrix width × zoom (at 128 px and zoom 6 that is 768 px), the
browser scales the **image** down. The **widget frames** were still placed in unscaled zoom
pixels. Measured at 1400 px window width: stage 715 px wide, content 770 px, six elements past
the edge — visible in the form next to it.

Fixed with a third factor `K.skala` (actual ÷ natural image width) which both places the
frames and converts the drag paths — otherwise the widget would have wandered out from under
the mouse pointer. Measured afterwards: 0 elements past the edge.

⚠ Two traps along the way, both hit while building:

- `clientWidth` is **0** as long as the tab is hidden (`section[hidden]`). Without a fallback
  to factor 1 all frames collapsed to size zero.
- The factor changes when dragging the window edge and when switching to the tab. Both now
  trigger the placement again.

## 0.11.4 — the hands at the ends of the rays were missing

The first crop for the icon took the disc plus the **upper** part of the rays — and cut off
exactly the **hands**, that is, the defining feature of the symbol. Criticised by the user,
rightly.

★ **The cut goes sideways, never horizontally.** Fewer rays (the middle 45 % of the width),
but whole ones: that way the symbol becomes almost square and fits into the icon without
loss. The thickening here is ×4 instead of ×2 as on the logo, because a square offers less
height — at 40 × 40 the symbol carries about 31 px.

Four variants were again compared at real display size. The reasoning is in the generator so
that the horizontal cut does not come back.

## 0.11.3 — one motif everywhere: the dot grid is gone

The Aton symbol now applies to **all** images, not just the logo:

| File | Size | where it appears |
|---|---|---|
| `aton/icon.png` | 128×128 | list of installed apps (shown at 40×40) |
| `aton/logo.png` | 524×256 | detail page of the app (shown at 82×40) |
| `aton/www/icon.png` | 256×256 | favicon and header of the app's own UI |
| `brand/icon.png` | 256×256 | PR to `home-assistant/brands` (integration tile) |
| `brand/icon@2x.png` | 512×512 | ditto, hDPI |

★ **The icon shows a CROP, not the whole symbol.** Aton is 2.3:1 wide; placed in a square it
would not be 14 px tall when HA shows the icon at 40×40 — the rays would then be 0.14 px wide
and simply absent. Four variants were compared at real size: the whole symbol turns into a
blob, the crop (disc plus upper part of the rays) carries and uses the square area.

The brands files are checked against the rules over there: exactly 256 resp. 512, square, PNG
with transparency, not byte-identical, no border.

## 0.11.2 — new logo: the Aton symbol, without lettering

At the user's request the logo now shows **Aton itself** — the sun disc with the rays ending
in hands — and no longer a wordmark.

The source is [Aten.svg](https://commons.wikimedia.org/wiki/File:Aten.svg) by AtonX.
⚠ The file is offered under a choice of licences; it is used under **CC BY 2.5**, the only
one among them WITHOUT share-alike — the least problematic for a published repository.
Attribution in the README, provenance and modifications in the image generator's provenance
note.

★ **The rays had to be thickened, otherwise they vanished.** In the original they are ~4 px
wide at 400 px height — at the 40 px HA shows the logo at, 0.5 px of that remain, and they
appear as olive-grey smears instead of golden rays. Five gradations compared at real display
size: from ×3 they merge into a fan, ×2 keeps them separate and golden. That exact value is
now in the generator, with the reasoning beside it.

## 0.11.1 — store entry: English description, legible logo

Looking at the store card it became apparent that two things were still German:

- **`description:`** in `config.yaml` — that is the text the app store shows. Now English,
  and without a full stop: Home Assistant appends a sentence of its own ("You can find more
  information on the page …"), so there used to be two full stops.
- **`logo.png`** carried a subtitle ("LED matrix as an information board for Home
  Assistant").

★ **With the logo the language was not the problem at all.** The store shows the banner about
180 px wide; a 1000 px image ends up at a fifth of that, and a line 14 px tall has less than
3 px left there — it is fundamentally illegible, no matter what it says. On top of that the
store shows the description right below it anyway.

**So the subtitle was dropped entirely**, and the wordmark now uses the full height.
Reproduced at store size and checked: "Aton" is clearly legible. Same for Renpet.

## 0.11.0 — documentation in English, with images

Preparation for publication. `README.md` and `aton/DOCS.md` are new and in English.

New under `docs/`:

- `getting-started.md` — from installation to the first image, with the screenshot of the
  Operations tab and a table of what can be read there.
- `yaml-reference.md` — every key with an example: gate, brightness, `led_pitch`, widgets,
  screen groups, **pages with unequal dwell times**, messages, fonts, custom icons,
  templates, entities in HA.
- `configurator.md` — tree, preview, form; creating, moving, checking, saving, backups; the
  two known limits (`on`/`off` in `map:`, comments on list entries).

`aton/DOCS.md` is deliberately the SHORT version without images — HA only shows this file in
the app UI and does not render images in it reliably. It links to the detailed pages.

All warnings from the previous documentation were carried over, none dropped — plus two that
surfaced while writing the example: a `gate.fallback` pointing at a non-existent entity counts
as OFF (then the app draws nothing at all), and `states(...) | round(0)` throws when the
entity is missing, because `states()` returns the text `unknown`.

## 0.10.5 — the UI is now genuinely bilingual

Until now only the configurator knew about languages. The **Operations tab** contained not a
single `T(` — "Operations", "Switch off", "Brightness", "Frames" were hard-coded. With an
English UI that produced a mix of both, which will not do for a publication.

- `index.html` moved consistently to `T()` and `data-i18n`; `statischeTexte()` fills
  everything with `data-i18n` generically, so a new label only needs the attribute. The German
  text stays in the markup as a fallback.
- 14 missing keys added in both languages; in the configurator "Template" and "fixed" had been
  left over.
- Number formatting follows the language (`de-DE` / `en-GB`) instead of being fixed to German.
- ⚠ **Only the label** of "Automatik" is translated — the VALUE stays `Automatik`, it goes to
  the server like that and appears as a position in the config.

### ★★ Three bugs that surfaced along the way

1. **`window.K` was always `undefined`.** `K` is a top-level `const`, and that does not create
   a property on `window`. Three checks depended on it and therefore never applied: the prompt
   about unsaved changes did not appear, the number format stayed German forever. Now
   `typeof K`.
2. On a language change the cards must be rebuilt. They remember that with **four** flags
   (`schalter`, `regler`, `vollbild`, `aufgebaut`); I had overlooked two of them — switch and
   slider then disappeared entirely. Now cleared generically.
3. `betriebNeuZeichnen` must be a function DECLARATION at top level, otherwise
   `konfigurator.js` cannot find it.

## 0.10.2 — the brightness response reported the old value

`POST /api/panel/<id>/helligkeit` read the value back after setting it, and `helligkeit()`
reads from HA's state mirror when a `brightness.entity` is configured. That only catches up
with the `state_changed` event — so the response claimed the OLD value (measured: set 30,
reported 23), and the next `/api/panels` poll contradicted the slider.

- `setze_helligkeit()` now returns the value **actually set** (after clamping to 1..255)
  instead of `True`, and `None` when it did not work. The endpoint reports that value instead
  of fetching it back.
- `helligkeit()` gives the value it set itself **priority until the mirror confirms it** — at
  most 10 s. After that the mirror wins again, so that a confirmation which never arrives
  (entity refuses, event lost) does not let the display claim something permanently that is not
  true.

That makes it the same rule as in the UI since 0.10.1, only one level deeper — and it now
applies to **every** caller of the API, not just our own configurator.

## 0.10.1 — the Operations view stops taking control out of your hands

The user had to toggle the screen selection "Fields 1-12" several times before it took; the
brightness slider felt the same.

Cause: every three seconds `betriebHolen()` wrote the server values back into **every**
control — even when nothing had changed. Whoever typed at the wrong moment was working against
that beat.

- **Values are only written when the server reports a DIFFERENT value than on the last poll.**
  At rest, slider and selection are not touched at all; image and read-only values keep
  updating as before. A change from outside (Home Assistant, a second browser) still arrives —
  because then the value is new.
- **Your own command is defended** until the server confirms exactly it
  (`wunschSetzen`/`wunschHaelt`). Previously a late response could write the old state back; it
  looked as if the click had not taken — whereupon you clicked again and worked against your
  own earlier command. A 15 s limit as an emergency brake, so that a lost command does not
  leave the display permanently on a wish that does not exist.
- The screen selection now calls `bedient()` on `pointerdown` and `focus` — the slider next to
  it had been doing that for ages, the selection nowhere.

## 0.10.0 — pages may stand for different lengths of time

Until now `wechsel_zyklen` applied to the whole screen: all pages stood equally long. Every
page now has its own field **"This page stands"** (`zyklen`). That allows "overview 2 cycles,
details only 1".

- **0 = as long as configured on the screen.** Whoever enters nothing notices nothing: with
  equal dwell times the arithmetic falls back to the old formula, cross-checked over 20 000
  points in time.
- `wechsel_zyklen` remains the **master switch**: if it is 0, nothing changes at all — even if
  individual pages carry a number. Otherwise the documented meaning "0 = only the first" would
  be true sometimes and not others.
- The calculation still uses the **clock**, not a frame counter: two panels must not drift
  apart, and the preview in the configurator must not count the change along.

## 0.9.0 — identifier carried through: slug, domain, file names

0.8.0 had only renamed the NAMES; slug and integration domain stayed `matrix_panel`. At the
user's request now completely:

- `slug: matrix_panel` → **`aton`** (app is called `local_aton`)
- `DOMAIN = "matrix_panel"` → **`aton`**, directory `custom_components/aton`
- self-registration with the supervisor: `service: aton`
- `config_file: matrix_panel.yaml` → **`aton.yaml`**
- `matrix_icons` → **`aton_icons`**, `matrix_fonts` → **`aton_fonts`**
- backup folder → **`aton_sicherungen`** (the old folder is moved once)
- services `matrix_panel.notify` → **`aton.notify`**, `.notify_clear` accordingly

⚠ **This is a break, not a rename.** The integration has to be set up again; devices and
entities are created NEW in the process. The entity IDs are formed from the CURRENT display
name — not from the one that applied when they were first created. In the author's
installation `select.matrix_living_room_fields_1_8` afterwards became
`select.matrix_living_room_side_fields_1_12`: the old ID still dated from a time before the
"Side" suffix AND before the group grew from 8 to 12 fields.

**Anyone updating should know beforehand which entity IDs appear in automations, scripts,
dashboards and device firmware** — they may all change.

## 0.8.0 — now called Aton

Renamed after the Egyptian sun god: the sun disc whose rays end in hands — a surface that
emits light. Fits Osiris, Horus, Anubis and the other devices in the house. German spelling
(Aton, as in Akhenaton), not Aten.

**Only names** were changed: app name, sidebar entry, title of the UI, name of the companion
integration, repo URL and the directories (`matrix_panel/` → `aton/`).

⚠ **Deliberately NOT changed**, because existing state depends on it:

- `slug: matrix_panel` — the add-on slug stays `local_matrix_panel`.
- `DOMAIN = "matrix_panel"` of the companion integration.
- This keeps **device and all entities** including their `unique_id`. A change would create a
  complete second set of entities and leave the old ones as `unavailable` — and the Osiris
  firmware has an entity ID hard-wired.
- `config_file: matrix_panel.yaml` and the folders `matrix_icons` / `matrix_fonts` in
  `/config` — that is the user's data, not the app's names.

Slug, domain and file names belong in a conversion of their own with a migration path,
sensibly bundled with publication.

## 0.7.0 — 2026-08-06

**★★ The identifier of the UI files now sits in the FILE NAME, not in the query part** —
`static/konfigurator.1785971601.js` instead of `static/konfigurator.js?v=…`.

The reason is proven on the device and was expensive: `…js?v=123` looks like `…js` to a
service worker. It is allowed to ignore the query when looking up and answer with an old copy —
no matter which identifier is attached. That is exactly what happened: the server demonstrably
served the new file (measured through Ingress), the browser executed the old one for hours,
and **every** server-side measure remained ineffective.

In the end it was recognisable at a single place: the data in the browser was new (`seiten`
present), the display showed `0` — and `0` is exactly what the OLD code produces on NEW data
(`(sc.widgets || []).length`, where there is no `widgets` any more).

A different **path** is a different entry in the cache. There is no way around that. On disk
`konfigurator.js` still lies there; a handler maps the name with the identifier back onto it.

## 0.6.5 — 2026-08-06

**The stale-version warning never ran in the configurator of all places.** It hung in
`betriebHolen()`, which aborts immediately as soon as the Operations tab is not visible.
Whoever works in the configurator — that is, where an old version does the most damage — never
got to see it; "the yellow box is gone" did not mean "everything is current" there, but
"nothing is being checked here".

Now it has its own beat (every 15 s, on **every** tab) against the new, tiny endpoint
`/api/stand`.

## 0.6.4 — 2026-08-06

**The stale-version hint was ALWAYS visible** — with empty text and a button that
consequently did nothing, because there was nothing to fix. Cause: `#veraltet` has its own
`display: flex`, and that overrides the `hidden` attribute (which is only a `display:none`
from the browser default and loses against any rule of your own). Fixed with
`#veraltet[hidden] { display: none; }`.

⚠ This made the hint worthless in 0.6.1–0.6.3: it did not indicate that something was stale,
it was simply always there.

## 0.6.3 — 2026-08-06

**"Reload" reloaded — and still showed the old page.** This UI runs under HA's Ingress in an
embedded frame, and HA's frontend has a service worker. It sits **in front of** the network and
may answer the same address from its cache — the `no-store` the app sends never even reaches
it.

The button now loads with a **different address** (`?neu=<timestamp>`, via `location.replace`).
Caches are keyed by the full address; a new parameter is a miss in it and forces the trip to
the network.

## 0.6.2 — 2026-08-06

**The "Reload" button in the stale-version hint did nothing.** Two causes, both fixed:

- It hung as an `onclick` attribute in the page — the only one in the whole file, everything
  else attaches its handlers in JavaScript. Under delivery through HA's Ingress an inline
  attribute is the one way that silently does nothing.
- The configurator attaches a `beforeunload` guard as long as there are unsaved changes. In an
  embedded frame the browser then cancels the navigation **without asking** — the button looked
  broken. Now it asks explicitly and clears the flag beforehand.

## 0.6.1 — 2026-08-06

**The UI now says when an old version is running in the browser.** Twice in one evening that
was the cause of a long search: the server had long been serving the new version, the tab was
running the old one — and you cannot see that from a page. Every observation is then
provisional.

`/api/panels` (fetched every three seconds anyway) delivers the version the server is *currently*
serving. If it differs from the one the page was loaded with, a hint appears at the top with a
"Reload" button.

⚠ The `?v=` identifier on the scripts is correct (modification time per file) — but it only
helps on the NEXT load. A tab that has been open for hours notices nothing of a new version.
That is exactly the gap the hint closes.

## 0.6.0 — 2026-08-06

**★★ A screen can now have several `seiten:` — and they take turns.** That way the same widgets
alternately show temperature and humidity **without** turning into two positions in the
selection.

That was the mistake in 0.5.16/0.5.17: the alternation sat between *screens*. But two screens
are two positions in Home Assistant's `select` — and a manual selection stopped the alternation,
because it pins exactly one position. Now the alternation sits **inside** the screen: the
selection still only shows "Temperatures", and the change happens both on automatic and on
manual selection.

⚠ **Move:** `wechsel_zyklen` belongs on the SCREEN, no longer on the group. If it is still on
the group, validation says so explicitly instead of "unknown key".

```yaml
- name: Temperatures           # one position in the selection
  when: always
  wechsel_zyklen: 2            # pages every 2 frame cycles
  seiten:
    - name: Temperature
      widgets: [ … °C … ]
    - name: Humidity
      widgets: [ … % … ]
```

A screen with `widgets:` instead of `seiten:` stays exactly as before — internally it then has
a single page. Both at once is rejected.

In the configurator, screens with pages get one more level in the tree; the click areas in the
preview image follow the **visible** page — otherwise you would unknowingly edit a widget you
cannot currently see.

## 0.5.18 — 2026-08-05

**★★ A faulty config no longer terminates the app.** Previously it did exactly that
(`return 1`) — with the nasty consequence that **the UI never came up either**: the error could
then only be fixed through the file editor or the console, that is, precisely not where the
config is otherwise maintained. On top of that the supervisor restarted the app in a loop.

Now it starts **without panels**, records the error and shows it in the Operations tab as a red
box with the exact place (`panels[0].screen_groups[0]: unknown keys: …`). Correct it, *Reload* —
done, without touching the app.

**Renamed fields are accepted instead of rejected.** The check for unknown keys is deliberately
strict (`valu` instead of `value` should fail loudly), but it also hit every rename.
Known-outdated names are now declared as such in the schema (`UMBENANNT`) and accepted with a
hint in the log — `wechsel_s: 10` becomes `wechsel_zyklen: 2` at a 5 s cycle. A genuine typo
still fails.

## 0.5.17 — 2026-08-05

**The alternation is now specified in cycles, not seconds** (`wechsel_zyklen` instead of
`wechsel_s`). A cycle is one frame interval — at `interval: 5` two cycles are ten seconds.
Reason: you think about this display in frames, not in seconds, and `full_frame_every` already
counts that way for the same reason. A value below one cycle, which could not take effect at
all, no longer exists.

⚠ **The calculation still uses the clock** (cycles × interval), not a frame counter: a real
counter would be incremented by the preview in the configurator, and two panels would drift
apart over time.

⚠ Anyone who tried 0.5.16 changes `wechsel_s: 10` to `wechsel_zyklen: 2`.

## 0.5.16 — 2026-08-05

**Screens of a group can take turns.** New field `wechsel_s` on the screen group
(configurator: *Change every*, seconds, 0 = off). This allows, for example, showing temperature
and humidity alternately on the same eight widgets instead of fitting both in side by side.

**The rule behind it:** only **equal-ranked** screens alternate — all those with the same
condition as the winner (`when: always` and a missing `when` are the same thing here). Order
therefore remains precedence: a conditional screen displaces the fallbacks as before, and
"several screens for the same case" now means alternation instead of "the first always wins".
Without `wechsel_s` nothing changes.

The point in time comes from the clock, not from a frame counter: that way the alternation does
not depend on how often something was rendered (preview in the configurator, redraw because of
a message), and two panels with the same interval run in sync instead of drifting apart. The
manual selection in Home Assistant still beats the alternation.

⚠ Shorter than the frame interval (`interval`) has no effect — at a 5 s interval, 5 s is the
finest sensible step.

## 0.5.15 — 2026-08-03

**★★ A panel without `gate.fallback` could get stuck beyond rescue.** Experienced on the
device: the small matrix lost its second segment when switched off and on. But Home Assistant
only creates the master switch **as long as the device has more than one segment** — the entity
stayed `unavailable` with `restored: true`, so the app never drew again, and it was precisely
the drawing that would have created the second segment. An HA restart did not help, because the
cause sat on the device.

Without a fallback the app now **draws when in doubt**. The attempt costs nothing: either it
succeeds — then the second segment comes into being, HA creates the master switch and everything
sorts itself out — or it fails and honestly reports a send error. Both are better than a
standstill with no way out.

⚠ Manual first aid should it ever occur — create the second segment directly:

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"seg":[{"id":1,"on":false,"frz":false,"start":0,"stop":1,"startY":<h-1>,"stopY":<h>}]}' \
  http://<matrix>/json/state
```

**The start-up leniency was drawn too narrowly.** It additionally required the gate to report
`unavailable` and a fallback to be configured. After switching on the large matrix via its
script a red box appeared anyway, because Home Assistant already reported the master switch as
`on` again although WLED was not yet on the network. The state of the gate says nothing about
whether the device **answers**. Now only the 60 s window after switching on counts.

## 0.5.14 — 2026-08-02

**The Operations view froze and the browser console filled up.** The cause was a name collision
that I armed myself in 0.5.11:

```
konfigurator.js:52  Uncaught TypeError: pfad is not iterable
    at hole (konfigurator.js:52)
    at .../index:395        ← setInterval(() => hole(), 3000)
    at nachfassen           ← follow-up loop of the switch
```

There are **two** functions called `hole` in the same global scope: the one from the Operations
view and `hole(pfad)` from `konfigurator.js`, which is loaded later and overwrites the first.
Harmless for a long time, because `setInterval(hole, 3000)` captured the reference immediately —
before the configurator was loaded. With the arrow function from 0.5.11 the name is looked up
again on **every** call and has hit the path helper ever since.

The Operations view's function is now called `betriebHolen`. Verified: between the embedded
script, `konfigurator.js` and `symboleditor.js` there are **no** shared global names left.

## 0.5.13 — 2026-08-02

**A single failed request could wedge the UI.** `hole()` caught nothing — if the request fails
(for instance because the app is restarting), the chain breaks. For the timer that would be
harmless, for the switch's follow-up loop it is not: it then aborts and leaves the button
**disabled forever**. Likewise for the switching call itself — if it fails, the button is now
released in every case.

No substitute for a reload: if an older version of the page is still running in the browser,
only Ctrl-Shift-R helps. The **build stamp next to the title** says which version is loaded.

## 0.5.12 — 2026-08-02

**After switching on via a switch script a red error box appeared.** Not a false alarm in the
narrow sense — the app really did send into the void. Measured on the device:

```
20:10:18.86  script.toggle_side_matrix → on    (click)
20:10:19.02  switch.matrix_relay       → on    (power on)
20:10:39.06  light.matrix_power        → on    (WLED on the network, 20 s later)
```

During those 20 seconds the gate is `unavailable`. Then the fallback to the power switch
applies — which says `on`, so the app considers itself entitled to draw and runs into timeouts.
Such errors now pass as "starting up" for up to 60 seconds after switching on, instead of
appearing as an alarm.

⚠ Deliberately with a time limit: a device that does not come up at all reports honestly again
after a minute. The cumulative error counter stays in every case — that it grated should remain
visible.

## 0.5.11 — 2026-08-02

**The brightness slider stuttered while dragging.** Protecting the value from being overwritten
was not enough: the refresh still ran every three seconds, fetched a new preview image for
**every** panel and rebuilt the card — that stalls, and precisely under the finger that is
dragging. During operation nothing is refreshed at all now; four seconds after letting go it
continues. Triggered on touch-down already (`pointerdown`, covers mouse, finger and stylus), not
only on the first value change.

Actions by the user override the pause — they come from them, after all.

⚠ A trap avoided in the process: `setInterval(hole, 3000)` would have slipped `hole` the timer
argument as "force" and rendered the pause ineffective. Now via an arrow function.

## 0.5.10 — 2026-08-02

**"Send full frame" appeared twice.** The button had existed for a while — between the screen
selectors. When moving it into the control row I duplicated it instead of relocating it. The old
one is gone. (There it was called `b` and thereby shadowed the control row `b` from further up —
a mix-up that would have got expensive the next time anyone reached for it.)

## 0.5.9 — 2026-08-02

**"Send full frame" is now in the Operations tab**, in the same row as switch and brightness. It
applies to every panel regardless of whether a gate is configured — previously the only way was
via the entity in Home Assistant. Useful when something is on the matrix that the app did not
draw.

**★ Brightness arrived at the device up to five minutes late.** It rides on the `rahmen`, and
that only went out **with a full frame** — at `full_frame_every: 60` and a 5 s interval, only at
the next scheduled full frame. The slider therefore appeared to have no effect at all. On a
change it is now explicitly re-sent; on an unchanged value it is not, otherwise it would be one
more request every 5 seconds for something that hardly ever moves.

⚠ The app sets the **segment** brightness, not WLED's global one. That is why WLED's own value
stays in its UI — the two multiply. That is deliberate: WLED's global slider belongs to the user.

**The brightness slider jumped back while dragging.** Every three seconds the view fetches the
values and writes them into the controls. Checking `document.activeElement` is not enough when
operating with a finger or after clicking beside it — now additionally a grace period of four
seconds from the last touch.

**The on/off switch reacts faster.** It stayed stubbornly disabled for three seconds although a
directly switched gate reports the new state within fractions of a second. Now it follows up
briefly and releases as soon as the state has really flipped — with a switch script still
patiently up to 45 s, because booting, config entry and full frame happen in between. Whether a
script is involved is now stated by the server's response, instead of the UI guessing from the
message text.

## 0.5.8 — 2026-08-02

**The switch only knew one direction.** The event handler is created once when the card is built
and captures the `p` of exactly that pass; later refreshes create a new one. The label therefore
dutifully alternated between *switch on* and *switch off*, but the click always sent the
direction from the first draw — in the log three times `turn_off` and not a single `turn_on`. The
current state now hangs on the element instead of in the closure. ⚠ It only showed up on the
second matrix: the first switches via a script, and a script knows no direction.

**The switch is in front of the slider again.** If it appeared later — because the gate was not
yet configured at the first draw — it ended up behind the brightness slider and the cards looked
different. `prepend` instead of `appendChild`.

**★ After switching on, a full frame is forced.** WLED restores its own last state when switched
on — depending on the preset a colour or an effect. The app knew nothing about it and only sent
the differences to the image *it* had last sent; on the matrix everything it had not drawn itself
stayed put. Experienced on the device: after switching on, the surface was completely red and
stayed that way until the next scheduled full frame — at `full_frame_every: 60` and a 5 s
interval, up to five minutes. Also affects switching on from Home Assistant, not just the button
in the app.

## 0.5.7 — 2026-08-02

**A `gate:` or `brightness:` could not be entered at all on a panel that had none yet.**
`setze()` walked the path levels without creating missing ones — the assignment then threw a
TypeError and the input vanished **without a word**. It hit exactly the freshly created panels;
anyone editing one with an existing block never noticed. Missing levels are now created (a list
for a numeric index, otherwise a mapping); when *clearing* a field nothing is created on purpose,
otherwise empty branches would appear in the file.

## 0.5.6 — 2026-08-02

**The brightness slider was missing on every panel without a `gate:` block.** Switch and slider
sat in a shared `if (… && p.schaltbar)` — so whoever had no gate entry got no slider either,
although brightness has nothing to do with the gate (the companion integration creates its own
`number` entity for it anyway). Both are now built separately, each with its own flag. Side
effect: if a gate appears later because the device had no power, the switch is added afterwards
instead of being missing until the page is reloaded.

## 0.5.5 — 2026-08-02

**No more scrollbar under the preview image.** The image has `max-width: 100%` and a 1 px border —
with the CSS default `content-box` the border counts *on top*, so the image was 2 px wider than
its container. `box-sizing: border-box` fixes it.

**No more flicker on refresh.** `img.src = new` throws the old image away immediately and only
then loads; in the meantime the element has no size, the card collapses and everything below jumps
up. Now the new image is fetched first and then swapped — via a blob, because the response carries
`Cache-Control: no-store` and a second access to the same address would be a second transfer. If
fetching fails, the old image stays.

**Devices can be deleted now.** The companion integration had no `async_remove_config_entry_device`
— so Home Assistant did not even offer deletion ("Config entry does not support device removal").
Whoever changed a panel's identifier or removed a panel kept the old device in the overview
forever. Deletion is permitted exactly when the app no longer knows the panel; a device belonging
to a running panel stays protected.

⚠ **About a panel's identifier:** it forms the `unique_id` and the device identifier. If it is
changed, HA creates a **complete second set** of entities and the old one is left as `unavailable`
— together with everything that depends on it (dashboard cards, firmware with a hard-wired entity
ID). The **name**, by contrast, is freely changeable: the entity ID is created once and stays.

## 0.5.4 — 2026-08-02

**The card of a deleted or renamed panel stayed in the Operations tab.** Cards are recognised by
`p-<identifier>` and were only ever created, never removed — whoever changed the identifier kept
seeing the old card, with frozen values. It is cleaned up now. Along the way, the order of the
cards follows the config file again, even after re-sorting.

**New: `led_pitch` per panel** — the pitch of the matrix in millimetres (P3 = 3.0). Affects only
the presentation, never what is sent: the preview is scaled relative to it so that two panels sit
side by side in their real size ratio, and the LEDs are drawn as dots instead of abutting squares.
Without the entry nothing changes.

Scaling, grid and dots now live in **one** function shared by the Operations tab and the
configurator — previously the same procedure stood in two places, exactly the duplication the
comment on `pixelraster` had already warned about.

⚠ Two traps avoided, both only noticed while measuring: the configurator wrote the zoom *actually
used* back into the *requested* one — with `led_pitch` the image would have shrunk further on every
pass (6 → 5 → 4 → 3). And a typo in `led_pitch` or `interval` produced a bare `ValueError` instead
of the message with a path; both now go through `_float` and report
`panels[0].led_pitch: must be a number, is 'three'`.

## 0.5.3 — 2026-08-02

**The configurator always showed the first panel.** When switching to a second matrix the preview
image of the first stayed. Two causes, both only visible with a second panel:

- `K.panelIndex` had always been `0` and was **never set again** — preview and widget grid
  therefore referred permanently to `panels[0]`. The value is now **derived** from the selection in
  the tree instead of remembered; a state you can forget to update is one state too many.
- `waehle()` only re-fetched the preview when the *screen preselection* changed. Switching the
  panel triggered nothing at all. Now that is checked too.

The grid for dragging widgets hung on the same place and is therefore correct again as well.

## 0.5.2 — 2026-08-02

**Another panel can now be created in the configurator.** Previously that was only possible in the
config file: the tree provided an add path for widgets, screen groups and screens, but not for the
panel itself. The button `+ Panel` sits at the bottom of a panel's form — and under *Defaults*, so
that you can get at it even when none exists yet.

The new panel inherits size, grid, interval and `clear_segments_to` from the first existing one.
**`host` is deliberately left empty:** a made-up address would be worse than none, because the panel
would then silently send into the void or reach a foreign device.

**A hole in the validation was closed along the way.** `_pflicht` only checked whether a key was
*present* — so `host: ''` passed and would only have surfaced in operation as a request to
`http:///json/state`. Empty strings in required fields are now rejected (`panels[1]: 'host' is
empty`). Nothing changes for the existing config, cross-checked.

**The Operations tab places several panels side by side** as soon as the screen is wide enough, and
falls back to one column by itself on narrow devices. The 560 px minimum width is calculated: the
preview comes with `zoom=6`, so a 128-wide matrix is 768 px — with narrower columns the pixel
graphics would visibly soften. With only one panel nothing changes.

## 0.5.1 — 2026-08-02

**Backups no longer live in `/config`.** On saving, the copy now lands in the subfolder
`matrix_panel_sicherungen/` next to the config file. Previously they sat right beside it and
cluttered Home Assistant's file browser. Rotation already existed (the last 20 are kept), it was
just never visible — with 16 files the limit simply had not been reached. Backups from earlier
versions are moved into the folder by the app at startup, otherwise the cleanup would never find
them again.

**The red "not reachable" message stayed as long as the panel was off.** `letzter_fehler` was only
cleared by a successfully sent image — and with the panel switched off nothing is sent. When
switching off, one block typically still runs into a timeout, and that one send error then hung
around as a permanent warning. The message is now withdrawn as soon as the panel is deliberately
off; the cumulative counter stays. In addition the UI hides the "not reachable" marker when the
panel is off — it says nothing there that "panel off" does not already say.

## 0.5.0 — 2026-08-01

**On/off and brightness in the Operations tab.** A switch and a slider above the screen selectors.

The switch calls whatever is in `gate.script` — without an entry the app switches the gate
directly. The script is needed where more has to happen than power on: wait until the controller
has booted, activate HA's config entry, then a full frame. That order does not belong in a
rendering app.

★ A silent bug found along the way: `setze_helligkeit` only wrote an app-internal value. But that
is read exclusively when **no** `brightness.entity` is configured — so with a configured entity the
slider had no effect at all, without anything going wrong anywhere. Now it writes to the entity
(`input_number`/`number` via `set_value`).

For that, the HA connection can **write** for the first time (`call_service` over the WebSocket).
Deliberately kept narrow: one entity, one service, no free payload from outside. The domain comes
from the entity ID and is not hard-wired.

## 0.4.1 — 2026-08-01

**No more flicker every few minutes.** The full frame used to clear the surface explicitly and then
rebuild it in several requests — in between the matrix was dark. Now the full frame also encodes
the black runs and thereby describes the whole surface instead of merely adding to it. The clearing
is dropped entirely, and no pixel goes dark any more: each one is overwritten in place.

The recovery point is preserved — a pixel that does not belong there is now explicitly overwritten
in black instead of removed by clearing.

Price, measured on the real image (8192 pixels, 6803 of them black): 4782 instead of 2535 values,
34 instead of 18 kB of JSON, 7 instead of 4 blocks — every five minutes, on average about 54 bytes
per second.

## 0.4.0 — 2026-08-01

**Icon editor.** New tab *Icons*: paint pixels, save, done. Pen, eraser, eyedropper, fill/clear all,
40 steps of undo, palette plus free colour picker, five sizes (8×8 to 32×8). Bundled icons can be
opened and overwritten under the same name; deleting frees the bundled one again.

**With an alpha channel** — and that is not decoration: in the built-in icons black is transparent,
you cannot paint a black area there at all. A custom PNG can do both. That is why opacity is
separate from colour, and transparent pixels are shown by the grid as a chequerboard.

Saved to `/config/matrix_icons`. The running panel picks it up **immediately**: the icon registry
re-reads itself instead of being replaced — that way the panels keep their manual selection and
running messages.

## 0.3.0 — 2026-08-01

**Configurator.** Everything that can be in the config file can now be created and changed in the
UI — tab *Configuration* next to *Operations*.

- **Structure** on the left: the whole tree, expandable and collapsible, with the position per
  widget.
- **Preview** in the middle: click widgets **and drag** them. Grid widgets snap into cells and keep
  their `cell`, absolutely placed ones move pixel by pixel and keep their `at` — a `cell` never
  silently becomes an `at`. The notification row and a screen group's region appear dashed in yellow
  and can be moved the same way.
- **Forms** on the right, generated from the same description that validation uses. Entities are
  suggested with their current value, icons shown as an image grid, icon and colour configurable in
  all four forms (fixed, `map`, `steps`, `template`).
- **Creating** via a `+` on the branch in the tree; re-sorting, duplicating, deleting in the form.
- **Font rules** (`fonts:`) with a visible difference between built-in default and custom entry.
- **Two languages** (German, English); another one is a JSON file in `www/i18n/`.

The comments in the YAML survive saving: changes are made into the existing structure (ruamel in
round-trip mode), untouched places are not touched. A backup before every write, the last 20 are
kept. Anyone who edits the file in an editor alongside gets a warning instead of a silent overwrite.

⚠ **A bug in the display that only the configurator made visible:** `map: {off: dry, on: wet}` was
turned into `{False: 'dry', True: 'wet'}` by `yaml.safe_load` — YAML 1.1 turns `on`/`off` into
booleans. But the state of an HA entity is the string `"off"`, so the comparison always failed and
the `default` silently took over. On the matrix that meant: the rain icon permanently, in dry
weather. It was only noticed because the configurator (ruamel, YAML 1.2) drew a different icon than
the running panel. The file is now read so that `on/off/yes/no` stay strings; `true`/`false` stay
booleans.

Also fixed:

- **Reload** rebuilds fonts and icons as well. Previously a new file in `matrix_icons` stayed
  invisible and a change to `fonts:` had no effect until someone restarted the whole app.
- The **extent** of a widget is the union of icon box and text field, not the grid cell — a widget
  with its own `text_width` was otherwise only half selected.
- The **browser** showed the old UI after an update: the static files came without `Cache-Control`,
  and the page referenced them without an identifier. Now the modification time is attached to the
  references, and `/static/` answers with `no-cache`.

## 0.2.0 — 2026-07-31

**MQTT is out.** The controls in Home Assistant now come from a companion integration
(`custom_components/matrix_panel`, HACS-capable) that talks to the app over its HTTP interface.

Reason: through the supervisor service `mqtt` the app could only reach a broker that runs as an app.
Anyone running an **external** broker got "MQTT not available" — although MQTT was there. And anyone
not using MQTT at all would have had to introduce it just for the matrix.

In exchange there is now:

- a **device** per panel instead of loose entities, with a diagnostics section
- a **preview as an `image` entity** — the matrix image on the dashboard
- real **services** `matrix_panel.notify` / `.notify_clear` with fields and selection lists, instead
  of a JSON payload on a topic
- **self-registration**: the app registers with the supervisor, HA offers the integration for setup
  by itself. Host and port come along.

The app keeps running without the integration; you then operate it through its own UI.

⚠ Traps found along the way, documented in the code:

- **`GET /discovery` is not allowed for apps** (401), `POST` is. Cleaning up old registrations via
  the list fails — and is unnecessary, the supervisor deduplicates by itself.
- **No deregistration on shutdown.** HA may remove the config entry belonging to a deleted
  registration; throwing away the setup on every app restart would be a bad trade.

## 0.1.1 — 2026-07-31

Two blemishes from 0.1.0, both spotted by the user:

- `panel_icon` was set to `mdi:dot-grid` — **that icon name does not exist** (checked against the MDI
  source: 404, the correct one is `mdi:dots-grid`). The space in front of the name in the sidebar
  therefore stayed empty.
- `url` pointed at an invented host instead of the real one — affected `config.yaml` and
  `repository.yaml`.

⚠ Note for next time: a changed `config.yaml` is picked up by an INSTALLED app neither by
`ha apps reload` nor by `ha apps rebuild` — the supervisor keeps its own copy. It takes a **version
bump** and `ha apps update`.

## 0.1.0 — 2026-07-31

First version. **In production since 2026-07-31** on the living room matrix; the pyscript renderer
has been replaced and shut down.

- YAML config: panel → base image → screen groups with triggers
- image composition with Pillow, differential transmission to WLED, full frame as recovery point
- fonts: built-in 5x3, the same one as BDF, Spleen and Terminus bundled
- icons of the previous installation taken over unchanged, PNG icons additionally possible
- MQTT discovery: selection per screen group, diagnostics, full-frame button, brightness
- live preview through Ingress
- notification row with bar or WLED scrolling text

### Measured, not claimed

**Before the switchover, computationally:** `tools/parity_check.py` — 0 of 8192 pixels differing from
the pyscript renderer, in four cases (automatic, manual selection, short and long notification).
`tools/check_5x3_bdf.py` — 87/87 characters and 25/25 widget texts identical.

**After the switchover, on the device:** six comparisons of the app preview against the panel read
out over WLED's WebSocket — **0 structural differences** each time, in both screen positions.
Diagnostics in operation: 206 bytes per frame, 13 changed pixels, 0 send errors.

⚠ Colours **cannot** be compared directly in this way: WLED's live preview returns the values after
brightness and gamma correction (at brightness 23, `ffffff` becomes `5d5d5d`). What is compared is
which pixels are lit.

### Found and fixed during the switchover

- **s6 starts services with an empty environment** — without `#!/usr/bin/with-contenv bash` the app
  got no `SUPERVISOR_TOKEN`; that looked like broken credentials (MQTT 401, HA socket
  `auth_invalid`).
- **paho-mqtt 2.x** delivers a `ReasonCode` object in `on_connect`, not a number.
- **The full-frame anchor never was one**: WLED only clears a segment on an `i` write as long as it
  is not frozen — the image area runs with `frz: true`. A wrongly lit pixel therefore stayed forever
  (demonstrated on the device across 14 minutes and several anchors). Fixed by a range entry
  `[0, W*H, "000000"]` before the lit runs; after that the stuck pixel disappeared with the first
  full frame.
