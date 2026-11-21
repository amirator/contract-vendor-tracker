import json

from conftest import SAMPLE
from cvtrack.cli import main


def test_demo_end_to_end(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "drafts written (not sent)" in out
    for name in ("contract_vendor_tracker.xlsx", "weekly_summary.md", "summary.json", "control_sheet.png",
                 "reminders/outbox.csv"):
        assert (tmp_path / name).exists(), name
    s = json.loads((tmp_path / "summary.json").read_text())
    assert s["as_of"] == "2026-11-22" and s["reminders"] > 0
    assert "SAMPLE / DEMO DATA" in (tmp_path / "weekly_summary.md").read_text()


def test_as_of_override(tmp_path):
    assert main(["demo", "--out", str(tmp_path), "--as-of", "2027-06-01"]) == 0
    assert json.loads((tmp_path / "summary.json").read_text())["as_of"] == "2027-06-01"


def test_bad_input_returns_2(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.toml").write_text((SAMPLE / "config.toml").read_text())
    assert main(["run", "--data", str(tmp_path / "data"), "--out", str(tmp_path / "o")]) == 2
    assert "not found" in capsys.readouterr().out


def test_send_is_dry_run_by_default(tmp_path, capsys):
    main(["demo", "--out", str(tmp_path)])
    capsys.readouterr()
    assert main(["send", "--outbox", str(tmp_path / "reminders")]) == 0
    out = capsys.readouterr().out
    assert "nothing was sent" in out and "SENT" not in out
