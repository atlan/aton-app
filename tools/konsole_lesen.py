#!/usr/bin/env python3
"""Eine Seite in Chrome laden und mitschreiben, was die Konsole sagt.

Warum es das gibt: am 02.08.2026 hat die Betriebsansicht eingefroren, und die Ursache
stand die ganze Zeit in der Browser-Konsole (`TypeError: pfad is not iterable`). Von
aussen war nur zu sehen, dass der Server richtige Daten liefert und die Oberflaeche sie
nicht zeigt — daraus wurden zwei falsche Erklaerungen, bis der Benutzer den Auszug
geschickt hat. Mit diesem Werkzeug ist der Auszug eine Frage von Sekunden.

Zugang OHNE Home Assistant: die App laeuft in ihrem Container auf Port 8099 und braucht
dort keine Anmeldung. Ingress ist nur der Weg fuer Menschen.

    ssh -f -N -p 22222 -L 8099:<container-ip>:8099 root@<ha-host>
    python3 tools/konsole_lesen.py http://127.0.0.1:8099/

Die Container-IP liefert:
    docker inspect app_local_aton --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

⚠ Startet ein EIGENES Chrome mit eigenem Profilverzeichnis. Der laufende Browser des
Benutzers wird nicht angefasst — zwei Chrome-Instanzen auf demselben Profil vertragen
sich nicht.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222


def chrome_starten(profil: str) -> subprocess.Popen:
    return subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={profil}", "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ziel_holen(frist: float = 15.0) -> str:
    """Auf Chrome warten und die WebSocket-Adresse des Reiters liefern."""
    ende = time.time() + frist
    while time.time() < ende:
        try:
            mit = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1)
            for z in json.load(mit):
                if z.get("type") == "page":
                    return z["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.3)
    raise SystemExit("Chrome hat sich nicht gemeldet")


async def mitschreiben(ws_url: str, seite: str, dauer: float) -> list[str]:
    zeilen: list[str] = []
    async with websockets.connect(ws_url, max_size=None) as ws:
        nr = 0

        async def sende(methode: str, params: dict | None = None) -> None:
            nonlocal nr
            nr += 1
            await ws.send(json.dumps({"id": nr, "method": methode,
                                      "params": params or {}}))

        # ⚠ Beide Quellen anmelden: `Runtime.consoleAPICalled` bringt console.log/warn/error,
        # `Runtime.exceptionThrown` die NICHT abgefangenen Ausnahmen — und genau die waren
        # der Fund. Wer nur Ersteres abonniert, sieht den eigentlichen Fehler nicht.
        await sende("Runtime.enable")
        await sende("Log.enable")
        await sende("Page.enable")
        await sende("Page.navigate", {"url": seite})

        ende = time.time() + dauer
        while time.time() < ende:
            try:
                roh = await asyncio.wait_for(ws.recv(), timeout=max(0.1, ende - time.time()))
            except asyncio.TimeoutError:
                break
            n = json.loads(roh)
            m = n.get("method")
            p = n.get("params", {})

            if m == "Runtime.consoleAPICalled":
                text = " ".join(str(a.get("value", a.get("description", "")))
                                for a in p.get("args", []))
                zeilen.append(f"[{p.get('type', 'log')}] {text}")

            elif m == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                text = (d.get("exception", {}).get("description")
                        or d.get("text") or "Ausnahme")
                ort = ""
                rahmen = (d.get("stackTrace") or {}).get("callFrames") or []
                if rahmen:
                    f = rahmen[0]
                    datei = (f.get("url") or "?").rsplit("/", 1)[-1]
                    ort = f"  ({datei}:{f.get('lineNumber', 0) + 1})"
                zeilen.append(f"[AUSNAHME] {text.splitlines()[0]}{ort}")

            elif m == "Log.entryAdded":
                e = p.get("entry", {})
                if e.get("level") in ("error", "warning"):
                    zeilen.append(f"[{e.get('level')}] {e.get('text', '')}")
    return zeilen


def main() -> int:
    seite = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099/"
    dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0

    profil = tempfile.mkdtemp(prefix="chrome-konsole-")
    proc = chrome_starten(profil)
    try:
        zeilen = asyncio.run(mitschreiben(ziel_holen(), seite, dauer))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profil, ignore_errors=True)

    print(f"=== {seite} — {dauer:.0f} s mitgeschrieben ===")
    if not zeilen:
        print("  (nichts gemeldet — die Konsole blieb still)")
        return 0

    # Wiederholungen zusammenfassen: eine Ausnahme im 3-Sekunden-Takt fuellt sonst den
    # Bildschirm und verdeckt die seltenen, oft wichtigeren Meldungen.
    gesehen: dict[str, int] = {}
    for z in zeilen:
        gesehen[z] = gesehen.get(z, 0) + 1
    for text, n in gesehen.items():
        print(f"  {text}" + (f"   [{n}x]" if n > 1 else ""))
    return 1 if any(t.startswith(("[AUSNAHME]", "[error]")) for t in gesehen) else 0


if __name__ == "__main__":
    raise SystemExit(main())
