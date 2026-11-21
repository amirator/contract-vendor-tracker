import pytest

from conftest import invoice
from cvtrack.config import Config
from cvtrack.invoices import bucket_labels, evaluate_invoice, evaluate_invoices, invoice_summary


def due(days_past: int) -> str:
    from datetime import date, timedelta
    return (date(2026, 11, 22) - timedelta(days=days_past)).isoformat()


@pytest.mark.parametrize("dpd,bucket", [(-3, "Not yet due"), (0, "Not yet due"), (1, "1-30"), (30, "1-30"),
                                        (31, "31-60"), (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+")])
def test_bucket_boundaries(cfg, dpd, bucket):
    assert evaluate_invoice(invoice(due_date=due(dpd)), cfg).bucket == bucket


def test_paid_has_no_action(cfg):
    s = evaluate_invoice(invoice(status="Paid", due_date=due(50), paid_date="2026-11-01"), cfg)
    assert (s.bucket, s.action, s.is_open) == ("Paid", "", False)


@pytest.mark.parametrize("kw,action", [
    ({"due_date": due(-10)}, ""),                                              # not due soon yet
    ({"due_date": due(-5)}, "Due-soon nudge"),                                 # exactly due_soon_days before
    ({"due_date": due(3)}, "1st reminder"),
    ({"due_date": due(10), "chase_count": 1, "last_chased": due(8)}, "2nd reminder"),
    ({"due_date": due(10), "chase_count": 1, "last_chased": due(3)}, "Chased recently"),
    ({"due_date": due(31)}, "Escalate"),                                       # overdue > 30 days
    ({"due_date": due(5), "chase_count": 2, "last_chased": due(7)}, "Escalate"),  # 2 chasers already
    ({"due_date": due(5), "status": "Disputed"}, "Manual follow-up"),
    ({"due_date": due(-20), "status": "Awaiting vendor documents"}, "Due-soon nudge"),
    ({"due_date": due(-1), "status": "Approved - awaiting payment"}, ""),      # approved, not yet due
    ({"due_date": due(2), "status": "Approved - awaiting payment"}, "1st reminder"),
])
def test_next_action(cfg, kw, action):
    assert evaluate_invoice(invoice(**kw), cfg).action == action


def test_chase_gap_is_configurable():
    cfg = Config(as_of=__import__("datetime").date(2026, 11, 22), chase_gap_days=2)
    s = evaluate_invoice(invoice(due_date=due(10), chase_count=1, last_chased=due(3)), cfg)
    assert s.action == "2nd reminder"


def test_unknown_status_rejected(cfg):
    with pytest.raises(ValueError, match="unknown status"):
        evaluate_invoice(invoice(status="Lost"), cfg)


def test_custom_buckets_labels():
    cfg = Config(as_of=__import__("datetime").date(2026, 11, 22), ageing_buckets=(15, 45, 120))
    assert bucket_labels(cfg) == ["Not yet due", "1-15", "16-45", "46-120", "120+"]


def test_summary_reconciles_to_rows(demo):
    res, _ = demo
    inv = res["summary"]["invoices"]
    open_rows = [s for s in res["invoices"] if s.is_open]
    assert inv["open_count"] == len(open_rows) == sum(inv["ageing_count"].values())
    assert inv["open_amount"] == pytest.approx(sum(s.amount for s in open_rows))
    assert sum(inv["ageing_amount"].values()) == pytest.approx(inv["open_amount"])
    assert inv["overdue_amount"] == pytest.approx(sum(v for k, v in inv["ageing_amount"].items() if k != "Not yet due"))


def test_vat_is_15_percent_of_a_round_net(demo):
    res, _ = demo
    for s in res["invoices"]:
        net = s.amount / 1.15
        assert abs(net - round(net, -1)) < 0.01, s.row["invoice_id"]
