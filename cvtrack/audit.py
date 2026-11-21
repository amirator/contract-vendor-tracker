"""Audit-request log: who owes what to the auditors, by when, and what is late."""

from __future__ import annotations

from dataclasses import dataclass

from cvtrack.config import Config
from cvtrack.dates import business_days_until, parse

OPEN_STATUSES = ("Open", "In progress")
DONE_STATUSES = ("Submitted", "Closed")


@dataclass
class AuditStatus:
    row: dict
    days_open: int
    business_days_to_due: int
    days_overdue: int
    state: str
    escalate: bool

    @property
    def is_open(self) -> bool:
        return self.row["status"] in OPEN_STATUSES


def evaluate_request(row: dict, cfg: Config) -> AuditStatus:
    status = row["status"]
    if status not in OPEN_STATUSES + DONE_STATUSES:
        raise ValueError(f"{row['request_id']}: unknown status {status!r}")
    requested, due, submitted = parse(row["requested_date"]), parse(row["due_date"]), parse(row["submitted_date"])
    if requested is None or due is None:
        raise ValueError(f"{row['request_id']}: requested_date and due_date are required")
    if status in DONE_STATUSES and submitted is None:
        raise ValueError(f"{row['request_id']}: status {status} needs a submitted_date")
    bdays = business_days_until(cfg.as_of, due, cfg.weekend_idx)
    if status in DONE_STATUSES:
        days_open = (submitted - requested).days
        state = "Submitted on time" if submitted <= due else "Submitted late"
        overdue = 0
    else:
        days_open = (cfg.as_of - requested).days
        overdue = max((cfg.as_of - due).days, 0)
        if due < cfg.as_of:
            state = "Overdue"
        elif bdays <= cfg.audit_due_soon_business_days:
            state = "Due soon"
        else:
            state = "On track"
    escalate = state == "Overdue" and overdue > cfg.audit_escalate_days_overdue
    return AuditStatus(row, days_open, bdays, overdue, state, escalate)


def evaluate_requests(rows: list[dict], cfg: Config) -> list[AuditStatus]:
    return [evaluate_request(r, cfg) for r in rows]


def audit_summary(statuses: list[AuditStatus], cfg: Config) -> dict:
    open_ = [s for s in statuses if s.is_open]
    done = [s for s in statuses if not s.is_open]
    owners = sorted({s.row["owner"] for s in statuses})
    on_time = sum(s.state == "Submitted on time" for s in done)
    return {
        "total": len(statuses),
        "open": len(open_),
        "overdue": sum(s.state == "Overdue" for s in open_),
        "due_soon": sum(s.state == "Due soon" for s in open_),
        "escalations": sum(s.escalate for s in open_),
        "submitted": len(done),
        "on_time_rate": round(on_time / len(done), 4) if done else None,
        "avg_days_to_submit": round(sum(s.days_open for s in done) / len(done), 1) if done else None,
        "by_owner": {o: {"open": sum(s.row["owner"] == o for s in open_),
                         "overdue": sum(s.row["owner"] == o and s.state == "Overdue" for s in open_)} for o in owners},
    }
