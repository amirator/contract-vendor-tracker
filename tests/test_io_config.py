from datetime import date

import pytest

from conftest import SAMPLE
from cvtrack.config import load_config
from cvtrack.io import InputError, load_all, read_csv


def test_sample_files_have_banner_and_load():
    for f in SAMPLE.glob("*.csv"):
        assert f.read_text(encoding="utf-8").startswith("# SAMPLE / DEMO DATA")
    data = load_all(SAMPLE)
    assert {k: len(v) > 0 for k, v in data.items()} == {"contracts": True, "invoices": True,
                                                        "audit_requests": True, "vendors": True}


def test_missing_file_and_columns(tmp_path):
    with pytest.raises(InputError, match="not found"):
        read_csv(tmp_path / "nope.csv", "contracts")
    p = tmp_path / "c.csv"
    p.write_text("contract_id,title\nX,Y\n")
    with pytest.raises(InputError, match="missing column"):
        read_csv(p, "contracts")
    p.write_text("# banner only\n")
    with pytest.raises(InputError, match="no data"):
        read_csv(p, "contracts")


def test_config_load_and_override(tmp_path):
    cfg = load_config(SAMPLE / "config.toml")
    assert cfg.as_of == date(2026, 11, 22) and cfg.weekend == ("Fri", "Sat") and cfg.contract_bands == (30, 60, 90)
    assert load_config(SAMPLE / "config.toml", as_of=date(2027, 1, 1)).as_of == date(2027, 1, 1)
    bad = tmp_path / "c.toml"
    bad.write_text('as_of = "2026-01-01"\nweekend = ["Friday"]\n')
    with pytest.raises(ValueError, match="weekend"):
        load_config(bad)
    bad.write_text('as_of = "2026-01-01"\ncontract_bands = [90, 30, 60]\n')
    with pytest.raises(ValueError, match="ascending"):
        load_config(bad)
