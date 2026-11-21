"""Turn tracker results into reminder emails: one digest per recipient per topic.

Drafts are written as .eml (opens in Outlook, Thunderbird or Apple Mail) plus an .html preview.
Nothing is sent here; see mailer.py for the optional, dry-run-by-default SMTP sender.
"""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from cvtrack.audit import AuditStatus
from cvtrack.config import Config
from cvtrack.contracts import ContractStatus
from cvtrack.dates import next_business_day
from cvtrack.invoices import APPROVED, PENDING, VENDOR_DOCS, InvoiceStatus

NAVY, RED, AMBER, GREEN, GREY = "#1F2A44", "#C0392B", "#D68910", "#1E8449", "#5D6D7E"
RAG_COLOURS = {"Red": RED, "Amber": AMBER, "Green": GREEN, "Escalate": RED, "Overdue": RED, "Due soon": AMBER}


@dataclass
class Reminder:
    kind: str
    to_name: str
    to_email: str
    subject: str
    intro: str
    columns: list[str]
    rows: list[list[str]]
    highlight_col: int | None = None
    cc: list[str] = field(default_factory=list)
    greeting: str = ""
    item_ids: list[str] = field(default_factory=list)

    @property
    def escalated(self) -> bool:
        return bool(self.cc)


def _fmt_money(v: float, cfg: Config) -> str:
    return f"{cfg.currency} {v:,.0f}"


def _d(d) -> str:
    return d.strftime("%d %b %Y")


def _group(items, key):
    out: dict = {}
    for it in items:
        out.setdefault(key(it), []).append(it)
    return out


def contract_reminders(statuses: list[ContractStatus], cfg: Config) -> list[Reminder]:
    todo = sorted((s for s in statuses if s.needs_reminder), key=lambda s: s.days_to_expiry)
    out = []
    for (name, addr), items in _group(todo, lambda s: (s.row["owner"], s.row["owner_email"])).items():
        red = [s for s in items if s.rag == "Red"]
        rows = [[s.row["contract_id"], s.row["title"], s.row["vendor_name"], _d(s.end),
                 f"{s.days_to_expiry}" if s.days_to_expiry >= 0 else f"expired {-s.days_to_expiry} d ago",
                 _d(s.notice_deadline), s.notice_flag or "-", "Yes" if s.row["auto_renew"].upper() == "Y" else "No",
                 _fmt_money(float(s.row["annual_value_sar"]), cfg), s.rag] for s in items]
        n = len(items)
        out.append(Reminder(
            kind="contract-renewal", to_name=name, to_email=addr,
            subject=f"Contract renewals: {n} contract{'s' if n > 1 else ''} need{'' if n > 1 else 's'} a decision"
                    + (f" ({len(red)} urgent)" if red else ""),
            intro=(f"The contracts below end within {cfg.contract_bands[-1]} days, have already ended, or are close to "
                   "their notice deadline, and no renewal decision is recorded. Please reply with Renew, Re-tender "
                   "or Terminate for each one so the register can be updated."
                   + (" Contracts marked Red are copied to the escalation contact." if red else "")),
            columns=["Contract", "Title", "Vendor", "End date", "Days left", "Notice deadline", "Notice", "Auto-renew",
                     "Annual value", "RAG"],
            rows=rows, highlight_col=9, cc=[cfg.escalation_email] if red else [],
            item_ids=[s.row["contract_id"] for s in items]))
    return out


def invoice_reminders(statuses: list[InvoiceStatus], cfg: Config, vendors: dict[str, dict]) -> list[Reminder]:
    todo = [s for s in statuses if s.sends_email]
    out = []

    def recipient(s: InvoiceStatus):
        st = s.row["status"]
        if st == PENDING:
            return ("approver", s.row["approver"], s.row["approver_email"])
        if st == APPROVED:
            return ("ap", cfg.finance_ap_name, cfg.finance_ap_email)
        v = vendors.get(s.row["vendor_id"], {})
        return ("vendor", v.get("contact_name", s.row["vendor_name"]), v.get("contact_email", ""))

    for (role, name, addr), items in _group(todo, recipient).items():
        if not addr:
            continue
        items.sort(key=lambda s: -s.days_past_due)
        esc = [s for s in items if s.action == "Escalate"]
        total = _fmt_money(sum(s.amount for s in items), cfg)
        rows = [[s.row["invoice_id"], s.row["vendor_name"], s.row["po_number"] if "po_number" in s.row else "",
                 _d(datetime.fromisoformat(s.row["due_date"])),
                 f"{s.days_past_due} d overdue" if s.days_past_due > 0 else f"due in {-s.days_past_due} d",
                 _fmt_money(s.amount, cfg), s.action] for s in items]
        n = len(items)
        if role == "approver":
            subject = f"Invoice approvals: {n} invoice{'s' if n > 1 else ''} waiting for you ({total})"
            intro = ("These vendor invoices are waiting for your approval and are due for payment soon or already "
                     "overdue. Please approve, or reply with the reason they are on hold, so we can pay vendors on time.")
        elif role == "ap":
            subject = f"Approved invoices past due: {n} awaiting payment ({total})"
            intro = ("These invoices are approved but past their payment due date. Please confirm the payment run "
                     "date or let us know what is blocking payment.")
        else:
            subject = f"Documents needed to process your invoice{'s' if n > 1 else ''} ({n})"
            intro = (f"Dear {name}, we cannot process the invoices below until we receive the missing documents "
                     "(corrected tax invoice, delivery note or signed timesheet, as applicable). Please send them in "
                     "reply to this email. Thank you.")
        out.append(Reminder(kind=f"invoice-{role}", to_name=name, to_email=addr, subject=subject, intro=intro,
                            greeting="Dear colleagues," if role == "ap" else "",
                            columns=["Invoice", "Vendor", "PO", "Due date", "Status", "Amount", "Stage"], rows=rows,
                            highlight_col=6, cc=[cfg.escalation_email] if esc and role != "vendor" else [],
                            item_ids=[s.row["invoice_id"] for s in items]))
    return out


def audit_reminders(statuses: list[AuditStatus], cfg: Config) -> list[Reminder]:
    todo = sorted((s for s in statuses if s.state in ("Overdue", "Due soon")), key=lambda s: s.row["due_date"])
    out = []
    for (name, addr), items in _group(todo, lambda s: (s.row["owner"], s.row["owner_email"])).items():
        overdue = [s for s in items if s.state == "Overdue"]
        esc = [s for s in items if s.escalate]
        rows = [[s.row["request_id"], s.row["audit"], s.row["item"], _d(datetime.fromisoformat(s.row["due_date"])),
                 f"{s.days_overdue} d overdue" if s.state == "Overdue" else f"{s.business_days_to_due} working d left",
                 s.state] for s in items]
        n = len(items)
        out.append(Reminder(
            kind="audit-request", to_name=name, to_email=addr,
            subject="Audit requests: " + ", ".join(x for x in (
                f"{len(overdue)} overdue" if overdue else "",
                f"{n - len(overdue)} due within {cfg.audit_due_soon_business_days} working days" if n > len(overdue) else "",
            ) if x),
            intro=("The auditors are waiting for the items below. Please upload them to the shared audit folder and "
                   "reply to this email when done, or tell us the date you can deliver by."),
            columns=["Request", "Audit", "Item", "Due date", "Timing", "Status"], rows=rows, highlight_col=5,
            cc=[cfg.escalation_email] if esc else [], item_ids=[s.row["request_id"] for s in items]))
    return out


def _greeting(r: Reminder) -> str:
    return r.greeting or f"Dear {r.to_name.split()[0]},"


def render_html(r: Reminder, cfg: Config) -> str:
    head = "".join(f'<th style="text-align:left;padding:6px 8px;background:{NAVY};color:#fff;font-weight:600">'
                   f"{html.escape(c)}</th>" for c in r.columns)
    body = []
    for i, row in enumerate(r.rows):
        bg = "#F4F6F8" if i % 2 else "#FFFFFF"
        cells = []
        for j, v in enumerate(row):
            style = f"padding:6px 8px;border-bottom:1px solid #E5E8EC;background:{bg}"
            if j == r.highlight_col and v in RAG_COLOURS:
                style += f";color:{RAG_COLOURS[v]};font-weight:700"
            cells.append(f'<td style="{style}">{html.escape(str(v))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    banner = ('<p style="background:#FFF4CE;border:1px solid #E0C36A;padding:6px 10px;font-size:12px">'
              "SAMPLE / DEMO DATA: fictional company, people and amounts. Generated by contract-vendor-tracker; "
              "not sent.</p>") if cfg.sample_data else ""
    greeting = "" if r.intro.startswith("Dear") else f"<p>{html.escape(_greeting(r))}</p>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(r.subject)}</title></head>
<body style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1B1F24;max-width:960px">
{banner}{greeting}<p>{html.escape(r.intro)}</p>
<table style="border-collapse:collapse;font-size:13px;width:100%"><thead><tr>{head}</tr></thead>
<tbody>{''.join(body)}</tbody></table>
<p style="margin-top:16px">Kind regards,<br>{html.escape(cfg.sender_name)}<br>{html.escape(cfg.company)}</p>
<p style="color:{GREY};font-size:11px">Status as of {_d(cfg.as_of)}. This reminder was generated from the
contract and vendor tracker.</p>
</body></html>"""


def render_text(r: Reminder, cfg: Config) -> str:
    lines = []
    if cfg.sample_data:
        lines += ["SAMPLE / DEMO DATA: fictional company, people and amounts. Not sent.", ""]
    if not r.intro.startswith("Dear"):
        lines += [_greeting(r), ""]
    lines += [r.intro, ""]
    for row in r.rows:
        lines.append(" | ".join(f"{c}: {v}" for c, v in zip(r.columns, row)))
    lines += ["", "Kind regards,", cfg.sender_name, cfg.company, "", f"Status as of {_d(cfg.as_of)}."]
    return "\n".join(lines)


def build_message(r: Reminder, cfg: Config) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
    msg["To"] = f"{r.to_name} <{r.to_email}>"
    if r.cc:
        msg["Cc"] = ", ".join(r.cc)
    msg["Subject"] = ("[SAMPLE] " if cfg.sample_data else "") + r.subject
    send_day = next_business_day(cfg.as_of, cfg.weekend_idx)
    msg["Date"] = format_datetime(datetime.combine(send_day, time(8, 0), ZoneInfo("Asia/Riyadh")))
    msg["Message-ID"] = make_msgid(domain=cfg.sender_email.split("@")[1])
    msg["X-Unsent"] = "1"  # Outlook opens the .eml as an editable draft
    msg["X-Tracker-Items"] = ",".join(r.item_ids)
    if cfg.sample_data:
        msg["X-Sample-Data"] = "true"
    msg.set_content(render_text(r, cfg))
    msg.add_alternative(render_html(r, cfg), subtype="html")
    return msg


def write_drafts(reminders: list[Reminder], cfg: Config, out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in list(out_dir.glob("*.eml")) + list(out_dir.glob("*.html")):
        old.unlink()
    manifest = []
    for i, r in enumerate(reminders, start=1):
        local, domain = r.to_email.split("@")
        who = domain.split(".")[0] if r.kind == "invoice-vendor" else local.replace(".", "-")
        slug = f"{i:02d}_{r.kind}_{who}"
        (out_dir / f"{slug}.eml").write_bytes(bytes(build_message(r, cfg)))
        (out_dir / f"{slug}.html").write_text(render_html(r, cfg), encoding="utf-8")
        manifest.append({"file": f"{slug}.eml", "kind": r.kind, "to": r.to_email, "cc": ";".join(r.cc),
                         "subject": r.subject, "items": len(r.rows), "item_ids": " ".join(r.item_ids)})
    with (out_dir / "outbox.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "kind", "to", "cc", "subject", "items", "item_ids"])
        w.writeheader()
        w.writerows(manifest)
    return manifest
