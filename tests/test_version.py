"""The version has exactly one source, and it is `config.yaml`.

There used to be a second one: `panel/__init__.py` carried `__version__ = "0.1.0"`
while the app had long moved past 0.11. Nobody noticed, because nobody read it — which
is precisely why a duplicate like that survives. The supervisor reads `config.yaml`,
so that file wins, and anything else claiming to know the version is a future lie.

Since 0.11.8 the number also travels to Home Assistant: `/api/panels` reports it and
the companion integration writes it into the device as `sw_version`. A wrong number
would now be visible on the device page, which is a good reason to pin it down here.
"""
import re

from panel.const import APP_DIR, version


def _aus_config_yaml() -> str:
    """Read the version the way the supervisor does — plain text, no YAML parser."""
    with open(f"{APP_DIR}/config.yaml", encoding="utf-8") as fh:
        for zeile in fh:
            if zeile.startswith("version:"):
                return zeile.split(":", 1)[1].strip().strip("\"'")
    raise AssertionError("config.yaml has no version: line")


def test_version_kommt_aus_config_yaml():
    assert version() == _aus_config_yaml()


def test_version_sieht_aus_wie_eine_version():
    # Guards against the failure mode that made the old constant useless: something
    # that parses fine but means nothing.
    assert re.fullmatch(r"\d+\.\d+\.\d+", version()), version()


def test_kein_zweites_versionsfeld_im_paket():
    """`__version__` must not come back — a second source is the whole bug."""
    import panel

    assert not hasattr(panel, "__version__")
