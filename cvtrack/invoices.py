"""Vendor-invoice follow-up: ageing buckets and the next chaser for each unpaid invoice."""

from __future__ import annotations

from dataclasses import dataclass

from cvtrack.config import Config
from cvtrack.dates import parse

PAID = "Paid"
PENDING = "Pending approval"
APPROVED = "Approved - awaiting payment"
VENDOR_DOCS = "Awaiting vendor documents"
DISPUTED = "Disputed"
STATUSES = [PENDING, APPROVED, VENDOR_DOCS, DISPUTED, PAID]


@dataclass
class InvoiceStatus:
    row: dict
    amount: float
    days_past_due: int
    bucket: str
    action: str

    @property
    def is_open(self) -> bool:
        return self.row["status"] != PAID

    @property
    def sends_email(self) -> bool:
        return self.action in ("Due-soon nudge", "1st reminder", "2nd reminder", "Escalate")


def bucket_labels(cfg: Config) -> list[str]:
    edges = cfg.ageing_buckets
    labels = ["Not yet due"]
    lo = 1
    for e in edges:
        labels.append(f"{lo}-{e}")
        lo = e + 1
    labels.append(f"{edges[-1]}+")
    return labels


def bucket_for(dpd: int, is_open: bool, cfg: Config) -> str:
    if not is_open:
        return PAID
    labels = bucket_labels(cfg)
    if dpd <= 0:
        return labels[0]
    for e, label in zip(cfg.ageing_buckets, labels[1:]):
        if dpd <= e:
            return label
    return labels[-1]


def next_action(row: dict, dpd: int, cfg: Config) -> str:
    status = row["status"]
    if status == PAID:
        return ""
    if status == DISPUTED:
        return "Manual follow-up"
    last = parse(row["last_chased"])
    if last is not None and (cfg.as_of - last).days < cfg.chase_gap_days:
        return "Chased recently"
    chases = int(row["chase_count"] or 0)
    due_for_chase = (
        (status == PENDING and dpd >= -cfg.due_soon_days)
        or (status == APPROVED and dpd > 0)
        or status == VENDOR_DOCS
    )
    if not due_for_chase:
        return ""
    if dpd > cfg.escalate_after_days_overdue or chases >= cfg.escalate_after_chases:
        return "Escalate"
    if chases == 0:
        return "Due-soon nudge" if dpd <= 0 else "1st reminder"
    return "2nd reminder"


def evaluate_invoice(row: dict, cfg: Config) -> InvoiceStatus:
    if row["status"] not in STATUSES:
        raise ValueError(f"{row['invoice_id']}: unknown status {row['status']!r}; expected one of {STATUSES}")
    due = parse(row["due_date"])
    if due is None:
        raise ValueError(f"{row['invoice_id']}: due_date is empty")
    dpd = (cfg.as_of - due).days
    is_open = row["status"] != PAID
    return InvoiceStatus(row, float(row["amount_sar"]), dpd, bucket_for(dpd, is_open, cfg), next_action(row, dpd, cfg))


def evaluate_invoices(rows: list[dict], cfg: Config) -> list[InvoiceStatus]:
    return [evaluate_invoice(r, cfg) for r in rows]


def invoice_summary(statuses: list[InvoiceStatus], cfg: Config) -> dict:
    open_ = [s for s in statuses if s.is_open]
    labels = bucket_labels(cfg)
    return {
        "open_count": len(open_),
        "open_amount": round(sum(s.amount for s in open_), 2),
        "overdue_count": sum(s.days_past_due > 0 for s in open_),
        "overdue_amount": round(sum(s.amount for s in open_ if s.days_past_due > 0), 2),
        "ageing_amount": {b: round(sum(s.amount for s in open_ if s.bucket == b), 2) for b in labels},
        "ageing_count": {b: sum(s.bucket == b for s in open_) for b in labels},
        "by_status": {st: sum(s.row["status"] == st for s in open_) for st in STATUSES if st != PAID},
        "actions": {a: sum(s.action == a for s in open_) for a in
                    ("Due-soon nudge", "1st reminder", "2nd reminder", "Escalate", "Chased recently", "Manual follow-up")},
    }
