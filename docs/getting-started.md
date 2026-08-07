# Getting started

From nothing to a picture on the matrix. Roughly fifteen minutes, most of it waiting for
the add-on image to build.

## What you need

- A **WLED device** driving an LED matrix, reachable on your network, with its 2D setup
  already done in WLED itself (width, height, wiring). Aton draws pixels; it does not
  configure your panel layout.
- **Home Assistant with the supervisor** (HA OS or supervised) — this is an add-on.
- The IP address of the WLED device.

## 1. Install the app

**Settings → Add-ons → Add-on store → ⋮ → Repositories**, add the URL of this
repository. "Aton" then appears in the store; install and start it.

The first start builds the container image and takes a few minutes. When it is running,
"Aton" appears in the sidebar.

## 2. Write a description

Aton reads one file: `aton.yaml`, next to `configuration.yaml`. The quickest way is to
copy [`examples/aton.yaml`](../examples/aton.yaml) and change two things — the `host` and
the entity IDs.

The smallest description that works looks like this:

```yaml
panels:
  - id: hallway
    name: Hallway matrix
    host: 192.168.1.51
    size: [32, 16]
    dry_run: true
    widgets:
      - type: clock
        at: [0, 0]
        size: [32, 8]
      - type: text
        at: [0, 8]
        size: [32, 8]
        template: "{{ states('sensor.outdoor_temperature') | float(0) | round(0) }}°"
```

Two details in there are worth more than they look:

- **`dry_run: true`** means Aton computes the image and shows it in the preview but sends
  nothing. Start here. You can look at the result before anything reaches the panel.
- **`| float(0)`** before `round`. An entity that is missing or unavailable gives you the
  string `unknown`, and rounding a string raises an error. Filtering first is the single
  most common fix in a description.

## 3. Look at the preview

Open **Aton** in the sidebar. The *Operations* tab shows one card per panel.

![The operations tab](images/operations.png)

What to read here:

| | |
|---|---|
| **Display on / off** | whether the gate lets Aton draw at all |
| **Dry run – not sending** | the computed image is shown, the panel is untouched |
| **not reachable** | the device did not answer — check `host` |
| **Frames**, **Changed pixels**, **Bytes per frame** | proof that something is happening |
| **Send errors** | anything other than 0 means the transmission is failing |

The picture in the card is what Aton would send. If it looks right, you are one line away
from the real thing.

## 4. Go live

Set `dry_run: false` — in the configurator, or in the file followed by *Reload*. The next
cycle goes to the panel.

If nothing appears:

1. **Is the gate open?** With a `gate.entity` that is `off`, Aton deliberately draws
   nothing. The card says "Display off".
2. **Is the device reachable?** "not reachable" points at `host`, not at your
   description.
3. **Does WLED know its own geometry?** Aton sends pixels for `size`; if WLED is set up
   with a different width, the picture is scrambled rather than absent.

## 5. Optional: controls in Home Assistant

The app alone renders and can be operated from its own page. To get entities — a selector
per screen group, a preview image, diagnostic sensors, a full-frame button — install the
companion integration through HACS: add this repository as a *custom repository* of type
*Integration*, download "Aton", restart HA.

You do not have to type anything after that. The app announces itself to the supervisor,
and the integration appears under **Settings → Devices & services** as discovered, with
host and port already filled in.

## Where to go next

- [The configurator](configurator.md) — editing with a tree, a live preview and forms,
  instead of hand-writing YAML.
- [YAML reference](yaml-reference.md) — every key, including screen groups, pages,
  notifications, fonts and your own icons.
