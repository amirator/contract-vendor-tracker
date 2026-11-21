from datetime import date

import pytest

from conftest import audit_req
from cvtrack.audit import audit_summary, evaluate_request, evaluate_requests
from cvtrack.dates import business_days_until, next_business_day

FRI_SAT = {4, 5}
SAT_SUN = {5, 6}


def test_business_days_skip_fri_sat():
    thu, sun = date(2026, 11, 19), date(2026, 11, 22)
    assert business_days_until(thu, sun, FRI_SAT) == 1
    assert business_days_until(sun, thu, FRI_SAT) == -1  # Sat and Fri are skipped
    assert business_days_until(sun, date(2026, 11, 16), FRI_SAT) == -4  # back to Mon: Thu, Wed, Tue, Mon
    assert business_days_until(sun, sun, FRI_SAT) == 0
    assert business_days_until(date(2026, 11, 20), date(2026, 11, 23), SAT_SUN) == 1  # Fri -> Mon, Mon-Fri week


def test_next_business_day():
    assert next_business_day(date(2026, 11, 20), FRI_SAT) == date(2026, 11, 22)
    assert next_business_day(date(2026, 11, 22), FRI_SAT) == date(2026, 11, 22)


@pytest.mark.parametrize("due,state", [("2026-11-21", "Overdue"), ("2026-11-22", "Due soon"),
                                       ("2026-11-25", "Due soon"), ("2026-11-26", "On track")])
def test_open_states(cfg, due, state):
    # Sun 22 Nov: Mon 23, Tue 24, Wed 25 are 1-3 working days away; Thu 26 is 4
    assert evaluate_request(audit_req(due_date=due), cfg).state == state


def test_due_soon_counts_working_days_over_weekend(cfg):
    from cvtrack.config import Config
    thu = Config(as_of=date(2026, 11, 19))
    # Thu -> Tue is 3 working days (Sun, Mon, Tue) although it is 5 calendar days
    assert evaluate_request(audit_req(due_date="2026-11-24"), thu).state == "Due soon"


def test_submitted_on_time_and_late(cfg):
    on = evaluate_request(audit_req(status="Submitted", due_date="2026-11-10", submitted_date="2026-11-10"), cfg)
    late = evaluate_request(audit_req(status="Closed", due_date="2026-11-10", submitted_date="2026-11-12"), cfg)
    assert on.state == "Submitted on time" and late.state == "Submitted late"
    assert on.days_open == 9 and not on.is_open


def test_escalation_after_threshold(cfg):
    assert not evaluate_request(audit_req(due_date="2026-11-17"), cfg).escalate  # 5 days overdue
    assert evaluate_request(audit_req(due_date="2026-11-16"), cfg).escalate      # 6 days overdue


def test_bad_rows(cfg):
    with pytest.raises(ValueError, match="submitted_date"):
        evaluate_request(audit_req(status="Submitted"), cfg)
    with pytest.raises(ValueError, match="unknown status"):
        evaluate_request(audit_req(status="Lost"), cfg)


def test_summary(cfg):
    rows = [audit_req(due_date="2026-11-10"), audit_req(due_date="2026-12-30"),
            audit_req(status="Closed", due_date="2026-11-10", submitted_date="2026-11-09"),
            audit_req(status="Closed", due_date="2026-11-10", submitted_date="2026-11-12")]
    s = audit_summary(evaluate_requests(rows, cfg), cfg)
    assert (s["open"], s["overdue"], s["submitted"], s["on_time_rate"]) == (2, 1, 2, 0.5)
    assert s["by_owner"]["Own Er"] == {"open": 2, "overdue": 1}
