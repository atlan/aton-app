#!/usr/bin/env python3
"""Deutsche Feldtexte aus schema.py nach www/i18n/de.json ziehen.

Damit steht jeder Text genau einmal im Quelltext (in `schema.py`, wo er hingehört) und
liegt trotzdem als Katalog vor, gegen den man übersetzen kann.

Vorhandene Schlüssel in `de.json` werden NICHT überschrieben — die `ui.*`-Texte der
Oberfläche stehen nur dort und sollen erhalten bleiben. Nach einer Änderung an `schema.py`
also einfach neu laufen lassen; es kommt nur dazu, es verschwindet nichts.

    python3 tools/i18n_export.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from panel import schema  # noqa: E402

GRUPPEN = {
    "defaults": schema.DEFAULTS,
    "schrift_optionen": schema.SCHRIFT_OPTIONEN,
    "panel": schema.PANEL,
    "gate": schema.GATE,
    "brightness": schema.BRIGHTNESS,
    "grid": schema.GRID,
    "notify": schema.NOTIFY,
    "screen_group": schema.SCREEN_GROUP,
    "screen": schema.SCREEN,
    "widget": schema.WIDGET,
    "textquelle": schema.TEXTQUELLE,
}


def main() -> int:
    hier = os.path.dirname(os.path.abspath(__file__))
    ziel = os.path.abspath(os.path.join(hier, "..", "www", "i18n", "de.json"))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)

    vorhanden: dict[str, str] = {}
    if os.path.exists(ziel):
        with open(ziel, encoding="utf-8") as fh:
            vorhanden = json.load(fh)

    neu = 0
    for gruppe, felder in GRUPPEN.items():
        for f in felder:
            for teil, wert in (("label", f.label), ("hilfe", f.hilfe)):
                if not wert:
                    continue
                schluessel = f"schema.{gruppe}.{f.name}.{teil}"
                if schluessel not in vorhanden:
                    vorhanden[schluessel] = wert
                    neu += 1

    with open(ziel, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(vorhanden.items())), fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"{ziel}: {len(vorhanden)} Schluessel ({neu} neu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
