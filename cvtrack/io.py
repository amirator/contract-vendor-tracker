"""Read the tracker CSVs. Lines starting with '#' (the sample-data banner) are skipped."""

from __future__ import annotations

import csv
from pathlib import Path

REQUIRED = {
    "contracts": ["contract_id", "title", "vendor_name", "owner", "owner_email", "end_date", "notice_days",
                  "auto_renew", "annual_value_sar", "status", "renewal_decision"],
    "invoices": ["invoice_id", "vendor_id", "vendor_name", "invoice_date", "due_date", "amount_sar", "status",
                 "approver", "approver_email", "paid_date", "last_chased", "chase_count"],
    "audit_requests": ["request_id", "audit", "item", "owner", "owner_email", "requested_date", "due_date",
                       "status", "submitted_date"],
    "vendors": ["vendor_id", "vendor_name", "contact_name", "contact_email"],
}


class InputError(ValueError):
    pass


def read_csv(path: str | Path, kind: str) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise InputError(f"{path} not found")
    with path.open(encoding="utf-8-sig", newline="") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    rows = list(csv.DictReader(lines))
    if not rows:
        raise InputError(f"{path} has no data rows")
    missing = [c for c in REQUIRED[kind] if c not in rows[0]]
    if missing:
        raise InputError(f"{path} is missing column(s): {', '.join(missing)}")
    return rows


def load_all(data_dir: str | Path) -> dict[str, list[dict]]:
    data_dir = Path(data_dir)
    return {kind: read_csv(data_dir / f"{kind}.csv", kind) for kind in REQUIRED}
