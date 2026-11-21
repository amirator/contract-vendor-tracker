from datetime import date, timedelta

import pytest

from conftest import contract
from cvtrack.contracts import contract_summary, evaluate_contract, evaluate_contracts

AS_OF = date(2026, 11, 22)


def end_in(days: int) -> str:
    return (AS_OF + timedelta(days=days)).isoformat()


@pytest.mark.parametrize("days,band", [(-1, "Expired"), (0, "30-day"), (30, "30-day"), (31, "60-day"),
                                       (60, "60-day"), (61, "90-day"), (90, "90-day"), (91, "OK"), (400, "OK")])
def test_band_boundaries(cfg, days, band):
    assert evaluate_contract(contract(end_date=end_in(days)), cfg).band == band


def test_terminated_is_closed_and_has_no_rag(cfg):
    s = evaluate_contract(contract(end_date=end_in(10), status="Terminated"), cfg)
    assert (s.band, s.rag, s.notice_flag, s.needs_reminder) == ("Closed", "", "", False)


def test_notice_deadline_and_flags(cfg):
    s = evaluate_contract(contract(end_date=end_in(100), notice_days=90), cfg)
    assert s.notice_deadline == AS_OF + timedelta(days=10)
    assert (s.band, s.notice_flag, s.rag) == ("OK", "Notice due", "Amber")
    s = evaluate_contract(contract(end_date=end_in(80), notice_days=90, auto_renew="Y"), cfg)
    assert s.notice_flag == "Notice missed - auto-renews" and s.rag == "Red"
    s = evaluate_contract(contract(end_date=end_in(80), notice_days=90, auto_renew="N"), cfg)
    assert s.notice_flag == "Notice missed"


def test_decision_recorded_clears_flag_and_caps_at_amber(cfg):
    s = evaluate_contract(contract(end_date=end_in(5), notice_days=60, renewal_decision="Renew"), cfg)
    assert s.notice_flag == "" and s.rag == "Amber" and not s.needs_reminder


def test_rag_rules(cfg):
    assert evaluate_contract(contract(end_date=end_in(-3)), cfg).rag == "Red"
    assert evaluate_contract(contract(end_date=end_in(20), notice_days=10), cfg).rag == "Red"
    assert evaluate_contract(contract(end_date=end_in(75), notice_days=30), cfg).rag == "Amber"
    assert evaluate_contract(contract(end_date=end_in(200), notice_days=30), cfg).rag == "Green"


def test_missing_end_date_raises(cfg):
    with pytest.raises(ValueError, match="end_date"):
        evaluate_contract(contract(end_date=""), cfg)


def test_summary_counts_and_value(cfg):
    rows = [contract(end_date=end_in(d), annual_value_sar=v) for d, v in ((-5, 100), (10, 200), (95, 400))]
    rows.append(contract(end_date=end_in(10), status="Terminated", annual_value_sar=999))
    s = contract_summary(evaluate_contracts(rows, cfg), cfg)
    assert s["active"] == 3
    assert s["by_band"] == {"Expired": 1, "30-day": 1, "60-day": 0, "90-day": 0, "OK": 1}
    assert s["value_expiring_window"] == 200  # expired and terminated contracts are excluded
    assert s["undecided_in_window"] == 2


def test_sample_data_covers_every_band(demo):
    res, _ = demo
    bands = {s.band for s in res["contracts"]}
    assert {"Expired", "30-day", "60-day", "90-day", "OK", "Closed"} <= bands
