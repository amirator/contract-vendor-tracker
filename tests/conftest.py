from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cvtrack.config import Config, load_config

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_data"


@pytest.fixture
def cfg() -> Config:
    return Config(as_of=date(2026, 11, 22))  # Sunday


@pytest.fixture
def sample_cfg() -> Config:
    return load_config(SAMPLE / "config.toml")


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    from cvtrack.cli import run

    out = tmp_path_factory.mktemp("demo")
    return run(SAMPLE, out), out


def contract(**kw) -> dict:
    row = {"contract_id": "CT-T", "title": "Test", "vendor_name": "V", "owner": "Test Owner",
           "owner_email": "owner@x.example", "end_date": "2026-12-22", "notice_days": "30", "auto_renew": "N",
           "annual_value_sar": "1000", "status": "Active", "renewal_decision": "Pending"}
    row.update({k: str(v) for k, v in kw.items()})
    return row


def invoice(**kw) -> dict:
    row = {"invoice_id": "INV-T", "vendor_id": "V001", "vendor_name": "V", "po_number": "PO-1",
           "invoice_date": "2026-10-01", "due_date": "2026-11-01", "amount_sar": "1150.00",
           "status": "Pending approval", "approver": "Ap Prover", "approver_email": "ap.prover@x.example",
           "paid_date": "", "last_chased": "", "chase_count": "0"}
    row.update({k: str(v) for k, v in kw.items()})
    return row


def audit_req(**kw) -> dict:
    row = {"request_id": "AR-T", "audit": "A", "requested_by": "B", "item": "Item", "owner": "Own Er",
           "owner_email": "own.er@x.example", "department": "D", "priority": "High",
           "requested_date": "2026-11-01", "due_date": "2026-11-30", "status": "Open", "submitted_date": ""}
    row.update({k: str(v) for k, v in kw.items()})
    return row
