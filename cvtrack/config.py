"""Settings, read from a TOML file. Every rule threshold lives here, not in the code."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class Config:
    as_of: date
    company: str = "Demo Gulf Holding Co."
    currency: str = "SAR"
    weekend: tuple[str, ...] = ("Fri", "Sat")
    contract_bands: tuple[int, ...] = (30, 60, 90)
    notice_warning_days: int = 30
    ageing_buckets: tuple[int, ...] = (30, 60, 90)
    due_soon_days: int = 5
    chase_gap_days: int = 7
    escalate_after_days_overdue: int = 30
    escalate_after_chases: int = 2
    audit_due_soon_business_days: int = 3
    audit_escalate_days_overdue: int = 5
    sender_name: str = "Office of the COO"
    sender_email: str = "coo.office@demo-gulf-holding.example"
    escalation_name: str = "Head of Procurement"
    escalation_email: str = "procurement.head@demo-gulf-holding.example"
    finance_ap_name: str = "Accounts Payable team"
    finance_ap_email: str = "ap@demo-gulf-holding.example"
    sample_data: bool = True
    extra: dict = field(default_factory=dict)

    @property
    def weekend_idx(self) -> set[int]:
        return {DAY_NAMES.index(d) for d in self.weekend}


def load_config(path: str | Path, as_of: date | None = None) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    flat: dict = {}
    for section in raw.values():
        if isinstance(section, dict):
            flat.update(section)
    for k, v in raw.items():
        if not isinstance(v, dict):
            flat[k] = v
    known = set(Config.__dataclass_fields__) - {"extra"}
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in flat.items() if k in known}
    kwargs["extra"] = {k: v for k, v in flat.items() if k not in known}
    if as_of is not None:
        kwargs["as_of"] = as_of
    if isinstance(kwargs.get("as_of"), str):
        kwargs["as_of"] = date.fromisoformat(kwargs["as_of"])
    cfg = Config(**kwargs)
    bad = [d for d in cfg.weekend if d not in DAY_NAMES]
    if bad:
        raise ValueError(f"unknown weekend day(s) {bad}; use {DAY_NAMES}")
    if list(cfg.contract_bands) != sorted(cfg.contract_bands) or list(cfg.ageing_buckets) != sorted(cfg.ageing_buckets):
        raise ValueError("contract_bands and ageing_buckets must be in ascending order")
    return cfg
