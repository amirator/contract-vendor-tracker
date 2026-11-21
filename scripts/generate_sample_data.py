"""Regenerate the SAMPLE / DEMO CSVs in sample_data/ (deterministic, seed 2026).

Every company, person, contract, invoice and audit request is fictional. Dates are set
relative to the demo as-of date so each alert band, ageing bucket and chaser stage appears.
Run: python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"
AS_OF = date(2026, 11, 22)  # a Sunday, first day of the Sun-Thu work week
HEADER = "# SAMPLE / DEMO DATA - fictional company 'Demo Gulf Holding Co.'; not real contracts, vendors or people"

rng = random.Random(2026)

VENDORS = [
    ("V001", "Coastal Cleaning Demo Co.", "Facility services", "Huda Rahman", "coastal-cleaning"),
    ("V002", "Desert Cloud Demo LLC", "IT and cloud", "Omar Siddiqui", "desert-cloud"),
    ("V003", "Harbour Security Demo Co.", "Security services", "Faisal Qureshi", "harbour-security"),
    ("V004", "Palm Print & Office Supplies Demo", "Office supplies", "Mariam Yusuf", "palm-print"),
    ("V005", "Red Line Logistics Demo Co.", "Logistics", "Khalid Nasser", "redline-logistics"),
    ("V006", "Summit Legal Advisors Demo", "Legal services", "Rania Haddad", "summit-legal"),
    ("V007", "Oasis Catering Demo Co.", "Catering", "Yousef Karim", "oasis-catering"),
    ("V008", "Bright Lift Maintenance Demo", "Facility services", "Imran Shaikh", "bright-lift"),
    ("V009", "Gulf Fleet Leasing Demo Co.", "Vehicle leasing", "Nadia Farouk", "gulf-fleet"),
    ("V010", "Clearview Audit Software Demo", "IT and cloud", "Tariq Aziz", "clearview-soft"),
    ("V011", "Northgate Travel Demo Co.", "Travel management", "Salma Idris", "northgate-travel"),
    ("V012", "Keystone HVAC Demo Co.", "Facility services", "Bilal Hamdan", "keystone-hvac"),
    ("V013", "Atlas Telecom Demo Co.", "Telecom", "Lina Saeed", "atlas-telecom"),
    ("V014", "Meridian Insurance Brokers Demo", "Insurance", "Adel Mansour", "meridian-brokers"),
    ("V015", "Pioneer Training Demo Academy", "Training", "Hana Jaber", "pioneer-training"),
]

OWNERS = [  # internal contract / request owners (fictional)
    ("Layla Hassan", "Facilities"),
    ("Ahmed Karimi", "IT"),
    ("Noura Saleh", "Procurement"),
    ("Samir Douglas", "Finance"),
    ("Reem Abbas", "HR"),
    ("Yasir Malik", "Legal"),
    ("Dana Farah", "Office of the COO"),
]
APPROVERS = [("Samir Douglas", "Finance"), ("Noura Saleh", "Procurement"), ("Dana Farah", "Office of the COO"), ("Ahmed Karimi", "IT")]


def email(name: str) -> str:
    first, last = name.lower().replace("-", "").split(" ", 1)
    return f"{first}.{last.replace(' ', '')}@demo-gulf-holding.example"


def d(offset: int) -> str:
    return (AS_OF + timedelta(days=offset)).isoformat()


def write(name: str, rows: list[dict]) -> None:
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(HEADER + "\n")
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def vendors() -> list[dict]:
    rows = []
    for vid, name, cat, contact, dom in VENDORS:
        rows.append({
            "vendor_id": vid, "vendor_name": name, "category": cat, "contact_name": contact,
            "contact_email": f"accounts@{dom}.example", "city": rng.choice(["Jeddah", "Riyadh", "Dammam", "Jeddah"]),
        })
    return rows


CONTRACT_TITLES = {  # vendor_id -> plausible contract titles
    "V001": ["Office cleaning - HQ", "Pest control - all sites"],
    "V002": ["Cloud hosting and backup", "Laptop leasing and support"],
    "V003": ["Manned guarding - HQ and warehouse"],
    "V004": ["Stationery framework agreement"],
    "V005": ["Courier and document delivery"],
    "V006": ["External legal counsel retainer"],
    "V007": ["Pantry and meeting catering"],
    "V008": ["Lift maintenance - HQ tower"],
    "V009": ["Executive vehicle lease"],
    "V010": ["Audit-management software licences"],
    "V011": ["Corporate travel management"],
    "V012": ["HVAC preventive maintenance"],
    "V013": ["Mobile and data plans", "Internet leased line - HQ"],
    "V014": ["Medical insurance brokerage"],
    "V015": ["Leadership training framework"],
}

# (days_to_end, notice_days, auto_renew, status, decision) chosen to cover every alert case
CONTRACT_PLAN = [
    (-12, 30, "N", "Active", "Pending"),        # expired, nobody acted
    (-3, 60, "Y", "Active", "Pending"),         # expired auto-renew
    (6, 30, "Y", "Active", "Pending"),          # 30-day band, notice missed
    (14, 30, "N", "Under renewal", "Renew"),    # 30-day band, decided
    (27, 60, "Y", "Active", "Pending"),         # 30-day, notice missed, auto-renews
    (33, 30, "N", "Active", "Pending"),         # 60-day band, notice due in 3 days
    (45, 60, "Y", "Active", "Pending"),         # 60-day, notice missed
    (52, 30, "N", "Under renewal", "Re-tender"),
    (58, 90, "Y", "Active", "Renew"),
    (64, 60, "N", "Active", "Pending"),         # 90-day band, notice due in 4 days
    (71, 30, "Y", "Active", "Pending"),
    (80, 60, "N", "Active", "Pending"),
    (88, 90, "Y", "Active", "Pending"),         # notice missed already
    (90, 30, "N", "Active", "Pending"),         # boundary: exactly 90
    (30, 30, "N", "Active", "Pending"),         # boundary: exactly 30, notice due today
    (60, 30, "N", "Active", "Terminate"),       # boundary: exactly 60
    (-40, 30, "N", "Terminated", "Terminate"),  # terminated: excluded from alerts
]


def contracts(vrows: list[dict]) -> list[dict]:
    rows, n, seen = [], 1, {}
    sites = ["Riyadh branch", "Dammam office", "Warehouse", "Makkah site"]
    by_id = {v["vendor_id"]: v for v in vrows}
    plan = list(CONTRACT_PLAN)
    # add ordinary long-running contracts (OK band)
    for _ in range(19):
        plan.append((rng.randint(95, 700), rng.choice([30, 60, 90]), rng.choice(["Y", "N"]), "Active", "Pending"))
    rng.shuffle(plan)
    vids = list(CONTRACT_TITLES)
    for days_to_end, notice, auto, status, decision in plan:
        v = by_id[vids[(n - 1) % len(vids)]]
        cat = v["category"]
        title = rng.choice(CONTRACT_TITLES[v["vendor_id"]])
        seen[title] = seen.get(title, 0) + 1
        if seen[title] > 1:
            title = f"{title.split(' - ')[0]} - {sites[(seen[title] - 2) % len(sites)]}"
        term_years = rng.choice([1, 1, 2, 3])
        end = AS_OF + timedelta(days=days_to_end)
        start = end - timedelta(days=365 * term_years - 1)
        owner, dept = rng.choice(OWNERS)
        value = rng.choice([18, 24, 36, 48, 60, 75, 96, 120, 150, 240, 360, 480]) * 1000
        rows.append({
            "contract_id": f"CT-{n:03d}", "title": title, "vendor_id": v["vendor_id"], "vendor_name": v["vendor_name"],
            "category": cat, "owner": owner, "owner_email": email(owner), "department": dept,
            "start_date": start.isoformat(), "end_date": end.isoformat(), "notice_days": notice,
            "auto_renew": auto, "annual_value_sar": value, "status": status, "renewal_decision": decision,
        })
        n += 1
    return rows


INV_STATUS_PLAN = (
    ["Paid"] * 34 + ["Pending approval"] * 24 + ["Approved - awaiting payment"] * 14
    + ["Awaiting vendor documents"] * 9 + ["Disputed"] * 4
)


def invoices(crows: list[dict]) -> list[dict]:
    rows = []
    live = [c for c in crows if c["status"] != "Terminated"]
    statuses = list(INV_STATUS_PLAN)
    rng.shuffle(statuses)
    for i, status in enumerate(statuses, start=1):
        c = rng.choice(live)
        terms = rng.choice([30, 30, 45, 60])
        if status == "Paid":
            age = rng.randint(20, 150)
        else:  # most unpaid invoices are recent; a few have been stuck for months
            age = rng.randint(2, 45) if rng.random() < 0.75 else rng.randint(46, 140)
        inv_date = AS_OF - timedelta(days=age)
        received = inv_date + timedelta(days=rng.randint(1, 6))
        due = inv_date + timedelta(days=terms)
        net = round(int(c["annual_value_sar"]) / 12 * rng.uniform(0.6, 1.4), -1)
        gross = round(net * 1.15, 2)  # 15% VAT
        approver, _ = rng.choice(APPROVERS)
        paid_date = last_chased = ""
        chase_count = 0
        if status == "Paid":
            paid_date = min(AS_OF - timedelta(days=1), due + timedelta(days=rng.randint(-10, 20))).isoformat()
        elif due < AS_OF:
            chase_count = rng.choice([0, 0, 0, 1, 1, 2]) if (AS_OF - due).days < 30 else rng.choice([1, 2, 3])
            if chase_count:
                last_chased = (AS_OF - timedelta(days=rng.choice([2, 5, 9, 14, 21]))).isoformat()
        rows.append({
            "invoice_id": f"INV-{26000 + i}", "vendor_id": c["vendor_id"], "vendor_name": c["vendor_name"],
            "contract_id": c["contract_id"], "po_number": f"PO-{4500 + rng.randint(1, 899)}",
            "invoice_date": inv_date.isoformat(), "received_date": received.isoformat(), "due_date": due.isoformat(),
            "amount_sar": f"{gross:.2f}", "status": status, "approver": approver, "approver_email": email(approver),
            "paid_date": paid_date, "last_chased": last_chased, "chase_count": chase_count,
        })
    return rows


AUDIT_ITEMS = [
    ("External audit FY2026 - interim", "Demo Audit Partners (fictional)", [
        "Signed contracts above SAR 250k, with amendments", "Vendor master change log Jan-Oct", "Sample of 25 paid invoices with POs and GRNs",
        "Bank confirmation authority letters", "Fixed-asset additions listing", "Board-approved delegation of authority",
        "Accruals schedule at 30 Sep", "Legal confirmation letters", "Insurance policy schedule",
        "Lease agreements register", "Related-party transactions list", "Payroll-to-GL reconciliation (Sep)",
    ]),
    ("Internal audit - procurement review", "Internal Audit (Demo Gulf Holding)", [
        "Tender files for 3 largest awards", "Single-source justifications", "Conflict-of-interest declarations",
        "Contract renewal approvals 2026", "Three-quote evidence under SAR 100k", "Vendor performance evaluations",
        "PO vs invoice price variance report", "Emergency purchase log", "Approved vendor list with onboarding dates",
        "Contracts expired but still invoiced", "Duplicate-invoice check results", "Goods-received note sample (15 items)",
    ]),
    ("ZATCA e-invoicing readiness check (sample scope)", "Finance (Demo Gulf Holding)", [
        "List of invoicing systems", "Sample of 20 tax invoices with QR codes", "VAT return reconciliations Q1-Q3",
        "Credit and debit note sample", "Customer master data extract", "E-invoicing integration test evidence",
    ]),
]

# (requested_offset, due_offset, status, submitted_offset)
AUDIT_PLAN = [
    (-30, -9, "Open", None), (-25, -6, "In progress", None), (-21, -2, "Open", None), (-18, -1, "In progress", None),
    (-14, 0, "In progress", None), (-12, 1, "Open", None), (-10, 2, "In progress", None), (-9, 3, "Open", None),
    (-7, 5, "Open", None), (-5, 9, "Open", None), (-4, 12, "In progress", None), (-3, 14, "Open", None),
    (-40, -20, "Closed", -22), (-38, -18, "Closed", -16), (-36, -15, "Closed", -15), (-33, -12, "Closed", -9),
    (-31, -10, "Closed", -11), (-28, -8, "Submitted", -8), (-26, -5, "Submitted", -3), (-24, -4, "Closed", -6),
    (-22, -3, "Submitted", -4), (-20, -1, "Submitted", -1), (-45, -25, "Closed", -26), (-44, -24, "Closed", -19),
    (-15, 4, "Submitted", -2), (-13, 6, "Closed", -5), (-35, -14, "Closed", -14), (-19, -7, "Closed", -2),
    (-8, 7, "Open", None), (-6, 10, "In progress", None),
]


def audit_requests() -> list[dict]:
    rows = []
    items = [(a, by, it) for a, by, its in AUDIT_ITEMS for it in its]
    rng.shuffle(items)
    for i, ((req, due, status, sub), (audit, by, item)) in enumerate(zip(AUDIT_PLAN, items), start=1):
        owner, dept = rng.choice(OWNERS)
        rows.append({
            "request_id": f"AR-{i:03d}", "audit": audit, "requested_by": by, "item": item,
            "owner": owner, "owner_email": email(owner), "department": dept,
            "priority": rng.choice(["High", "Medium", "Medium", "Low"]),
            "requested_date": d(req), "due_date": d(due), "status": status,
            "submitted_date": d(sub) if sub is not None else "",
        })
    return rows


def main() -> None:
    OUT.mkdir(exist_ok=True)
    v = vendors()
    c = contracts(v)
    write("vendors.csv", v)
    write("contracts.csv", c)
    write("invoices.csv", invoices(c))
    write("audit_requests.csv", audit_requests())


if __name__ == "__main__":
    main()
