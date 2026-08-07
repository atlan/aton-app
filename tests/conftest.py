"""Shared test setup.

The tests target the parts where a silent bug is expensive: config parsing, the
config-file merge (it edits the user's own file), page rotation, and the brightness
decision. Rendering, the WLED transport and the web layer are deliberately left out —
testing those means testing our own mocks, and a rendering mistake is visible on the
panel within a second anyway.

⚠ `panel.display` imports `aiohttp` at module level although the decision logic does not
need it. Rather than making the test suite depend on a web client, we install a stub
before the import. If that import ever moves inside the functions that use it, this can
go away.
"""
import sys
import types
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1] / "aton"
sys.path.insert(0, str(WURZEL))

sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
