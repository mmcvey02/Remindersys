import sys

import pytest

from remindersys.cli import main
from remindersys.config import Config
from remindersys.notifier import _applescript_str, windows_toast_xml


def test_config_roundtrip_ignores_unknown(tmp_path):
    c = Config(home_address="Home", travel_mode="transit")
    c.save()
    raw = Config.path().read_text().replace('"travel_mode"', '"bogus": 1, "travel_mode"')
    Config.path().write_text(raw)
    loaded = Config.load()
    assert loaded.home_address == "Home" and loaded.travel_mode == "transit"


def test_notification_escaping():
    assert _applescript_str('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'
    xml = windows_toast_xml("A & B", "<x>", urgent=True)
    assert "A &amp; B" in xml and "&lt;x&gt;" in xml and 'scenario="reminder"' in xml


@pytest.fixture
def offline_config():
    Config(use_online_routing=False, open_summary_in_browser=False).save()


def test_cli_demo_sync(capsys, offline_config):
    assert main(["--demo", "sync"]) == 0
    out = capsys.readouterr().out
    assert "Planned notifications" in out


def test_cli_demo_summary(capsys, offline_config):
    assert main(["--demo", "summary", "weekly", "--no-browser"]) == 0
    assert "Week ahead" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="registry")
def test_autostart_roundtrip(tmp_path, monkeypatch):
    from remindersys import autostart

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    autostart.enable()
    assert autostart.is_enabled()
    autostart.disable()
    assert not autostart.is_enabled()
