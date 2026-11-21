"""Recalculate the workbook in LibreOffice (headless) and compare every formula cell with Python.

openpyxl writes formulas without cached results, so this is the check that the Excel formulas and
the Python rules agree. Needs LibreOffice (`soffice`) on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from cvtrack.workbook import FIRST


def soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def recalculated(xlsx: Path, dest_dir: Path) -> Path:
    exe = soffice()
    if not exe:
        raise RuntimeError("LibreOffice (soffice) not found on PATH")
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([exe, f"-env:UserInstallation=file://{profile}", "--headless", "--calc", "--convert-to", "xlsx",
                        "--outdir", str(dest_dir), str(xlsx)], check=True, capture_output=True, timeout=240)
    return dest_dir / xlsx.name


def _norm(v):
    if isinstance(v, datetime):
        return v.date()
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def compare(res: dict, xlsx: Path) -> list[str]:
    """Return a list of mismatches (empty list = formulas agree with Python)."""
    with tempfile.TemporaryDirectory() as tmp:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = load_workbook(recalculated(xlsx, Path(tmp)), data_only=True)
    bad: list[str] = []

    def check(sheet, row, col, got, want, ident):
        got = _norm(got)
        if got != want:
            bad.append(f"{sheet}!{col}{row} ({ident}): Excel={got!r} Python={want!r}")

    ws = wb["Contracts"]
    for i, s in enumerate(res["contracts"]):
        r, cid = FIRST + i, s.row["contract_id"]
        active = s.band != "Closed"
        check("Contracts", r, "O", ws[f"O{r}"].value, s.days_to_expiry if active else "", cid)
        check("Contracts", r, "P", ws[f"P{r}"].value, s.notice_deadline, cid)
        check("Contracts", r, "Q", ws[f"Q{r}"].value, s.days_to_notice, cid)
        check("Contracts", r, "R", ws[f"R{r}"].value, s.band, cid)
        check("Contracts", r, "S", ws[f"S{r}"].value, s.notice_flag, cid)
        check("Contracts", r, "T", ws[f"T{r}"].value, s.rag, cid)
    ws = wb["Invoices"]
    for i, s in enumerate(res["invoices"]):
        r, iid = FIRST + i, s.row["invoice_id"]
        check("Invoices", r, "M", ws[f"M{r}"].value, s.days_past_due if s.is_open else "", iid)
        check("Invoices", r, "N", ws[f"N{r}"].value, s.bucket, iid)
        check("Invoices", r, "P", ws[f"P{r}"].value, s.action, iid)
    ws = wb["Audit requests"]
    for i, s in enumerate(res["audit"]):
        r, rid = FIRST + i, s.row["request_id"]
        check("Audit", r, "L", ws[f"L{r}"].value, s.days_open, rid)
        check("Audit", r, "M", ws[f"M{r}"].value, s.business_days_to_due, rid)
        check("Audit", r, "N", ws[f"N{r}"].value, s.days_overdue, rid)
        check("Audit", r, "O", ws[f"O{r}"].value, s.state, rid)
        check("Audit", r, "P", ws[f"P{r}"].value, "Yes" if s.escalate else "", rid)

    d, sm = wb["Dashboard"], res["summary"]
    c, inv, au = sm["contracts"], sm["invoices"], sm["audit"]
    tiles = {"A6": c["active"], "B6": c["by_rag"]["Red"], "C6": c["notice_missed"], "D6": c["value_expiring_window"],
             "F6": inv["open_amount"], "G6": inv["overdue_amount"], "H6": au["open"], "I6": au["overdue"]}
    for cell, want in tiles.items():
        got = _norm(d[cell].value)
        if isinstance(want, float) or isinstance(got, float):
            if abs(float(got or 0) - float(want)) > 0.005:
                bad.append(f"Dashboard!{cell}: Excel={got!r} Python={want!r}")
        elif got != want:
            bad.append(f"Dashboard!{cell}: Excel={got!r} Python={want!r}")
    for k, (label, n) in enumerate(c["by_band"].items()):
        check("Dashboard", 11 + k, "A", d[f"A{11 + k}"].value, label, "band label")
        check("Dashboard", 11 + k, "B", d[f"B{11 + k}"].value, n, label)
    for k, label in enumerate(inv["ageing_amount"]):
        check("Dashboard", 11 + k, "F", d[f"F{11 + k}"].value, label, "bucket label")
        check("Dashboard", 11 + k, "G", d[f"G{11 + k}"].value, inv["ageing_count"][label], label)
        if abs(float(d[f"H{11 + k}"].value or 0) - inv["ageing_amount"][label]) > 0.005:
            bad.append(f"Dashboard!H{11 + k}: ageing amount mismatch for {label}")
    return bad
