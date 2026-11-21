"""Contract register: expiry bands (90/60/30 days), notice deadlines and RAG status.

The same rules are written as live formulas in the Excel workbook (see workbook.py);
tests check that both give identical results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from cvtrack.config import Config
from cvtrack.dates import parse


@dataclass
class ContractStatus:
    row: dict
    end: date
    days_to_expiry: int
    notice_deadline: date
    days_to_notice: int
    band: str
    notice_flag: str
    rag: str

    @property
    def needs_reminder(self) -> bool:
        return self.rag in ("Red", "Amber") and self.row["renewal_decision"] == "Pending"


def band_for(days: int, active: bool, bands: tuple[int, ...]) -> str:
    if not active:
        return "Closed"
    if days < 0:
        return "Expired"
    for b in bands:
        if days <= b:
            return f"{b}-day"
    return "OK"


def evaluate_contract(row: dict, cfg: Config) -> ContractStatus:
    end = parse(row["end_date"])
    if end is None:
        raise ValueError(f"{row['contract_id']}: end_date is empty")
    notice_days = int(row["notice_days"] or 0)
    active = row["status"] != "Terminated"
    decided = row["renewal_decision"] != "Pending"
    days = (end - cfg.as_of).days
    deadline = end - timedelta(days=notice_days)
    to_notice = (deadline - cfg.as_of).days
    band = band_for(days, active, cfg.contract_bands)

    flag = ""
    if active and not decided and days >= 0:
        if to_notice < 0:
            flag = "Notice missed - auto-renews" if row["auto_renew"].upper() == "Y" else "Notice missed"
        elif to_notice <= cfg.notice_warning_days:
            flag = "Notice due"

    first_band = f"{cfg.contract_bands[0]}-day"
    if not active:
        rag = ""
    elif not decided and (band in ("Expired", first_band) or flag.startswith("Notice missed")):
        rag = "Red"
    elif band != "OK" or flag == "Notice due":
        rag = "Amber"
    else:
        rag = "Green"
    return ContractStatus(row, end, days, deadline, to_notice, band, flag, rag)


def evaluate_contracts(rows: list[dict], cfg: Config) -> list[ContractStatus]:
    return [evaluate_contract(r, cfg) for r in rows]


def contract_summary(statuses: list[ContractStatus], cfg: Config) -> dict:
    live = [s for s in statuses if s.band != "Closed"]
    bands = ["Expired"] + [f"{b}-day" for b in cfg.contract_bands] + ["OK"]
    last = cfg.contract_bands[-1]
    return {
        "active": len(live),
        "by_band": {b: sum(s.band == b for s in live) for b in bands},
        "by_rag": {r: sum(s.rag == r for s in live) for r in ("Red", "Amber", "Green")},
        "notice_missed": sum(s.notice_flag.startswith("Notice missed") for s in live),
        "notice_due": sum(s.notice_flag == "Notice due" for s in live),
        "value_expiring_window": sum(float(s.row["annual_value_sar"]) for s in live if 0 <= s.days_to_expiry <= last),
        "undecided_in_window": sum(1 for s in live if s.days_to_expiry <= last and s.row["renewal_decision"] == "Pending"),
    }
