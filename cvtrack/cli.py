"""Command line: python -m cvtrack <command>. Run `python -m cvtrack --help`."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cvtrack import __version__
from cvtrack.audit import audit_summary, evaluate_requests
from cvtrack.config import load_config
from cvtrack.contracts import contract_summary, evaluate_contracts
from cvtrack.invoices import evaluate_invoices, invoice_summary
from cvtrack.io import InputError, load_all
from cvtrack.mailer import send_drafts
from cvtrack.reminders import audit_reminders, contract_reminders, invoice_reminders, write_drafts
from cvtrack.report import control_sheet_png, markdown_report, summary_text
from cvtrack.workbook import build_workbook

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "sample_data"


def run(data_dir: Path, out_dir: Path, config: Path | None = None, as_of: date | None = None,
        png: bool = True) -> dict:
    cfg = load_config(config or data_dir / "config.toml", as_of=as_of)
    data = load_all(data_dir)
    cs_rows = evaluate_contracts(data["contracts"], cfg)
    inv_rows = evaluate_invoices(data["invoices"], cfg)
    au_rows = evaluate_requests(data["audit_requests"], cfg)
    cs, inv, au = contract_summary(cs_rows, cfg), invoice_summary(inv_rows, cfg), audit_summary(au_rows, cfg)
    text = summary_text(cs, inv, au, cfg)
    vendors = {v["vendor_id"]: v for v in data["vendors"]}
    reminders = contract_reminders(cs_rows, cfg) + invoice_reminders(inv_rows, cfg, vendors) + audit_reminders(au_rows, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = write_drafts(reminders, cfg, out_dir / "reminders")
    xlsx = build_workbook(data, cfg, text, out_dir / "contract_vendor_tracker.xlsx")
    (out_dir / "weekly_summary.md").write_text(markdown_report(cs, inv, au, manifest, cfg), encoding="utf-8")
    summary = {"as_of": cfg.as_of.isoformat(), "contracts": cs, "invoices": inv, "audit": au,
               "reminders": len(manifest)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if png:
        control_sheet_png(cs, inv, au, cfg, out_dir / "control_sheet.png")
    return {"cfg": cfg, "summary": summary, "text": text, "manifest": manifest, "xlsx": xlsx,
            "contracts": cs_rows, "invoices": inv_rows, "audit": au_rows}


def _print_report(res: dict, out_dir: Path) -> None:
    s = res["summary"]
    c, i, a = s["contracts"], s["invoices"], s["audit"]
    print(f"Contract and vendor tracker - as of {s['as_of']}")
    print(f"  Contracts  active {c['active']:>3}  red {c['by_rag']['Red']:>2}  amber {c['by_rag']['Amber']:>2}  "
          f"notice missed {c['notice_missed']}  expired {c['by_band']['Expired']}")
    print(f"  Invoices   unpaid {i['open_count']:>3}  overdue {i['overdue_count']:>2}  "
          f"overdue SAR {i['overdue_amount']:>12,.2f}  escalate {i['actions']['Escalate']}")
    print(f"  Audit      open {a['open']:>5}  overdue {a['overdue']:>2}  due soon {a['due_soon']}  "
          f"on-time rate {a['on_time_rate']:.0%}")
    print(f"  Reminders  {len(res['manifest'])} drafts written (not sent)")
    print(f"Outputs in {out_dir}/: contract_vendor_tracker.xlsx, weekly_summary.md, summary.json, "
          f"control_sheet.png, reminders/*.eml|.html, reminders/outbox.csv")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m cvtrack", description="Contract and vendor tracker (sample data bundled).")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("demo", "run everything on the bundled SAMPLE data"),
                        ("run", "run everything on your own CSV folder")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--data", type=Path, default=DEFAULT_DATA, help="folder with the four CSVs and config.toml")
        sp.add_argument("--config", type=Path, default=None)
        sp.add_argument("--out", type=Path, default=Path("outputs"))
        sp.add_argument("--as-of", default=None, help="YYYY-MM-DD or 'today' (default: as_of in config.toml)")
    sp = sub.add_parser("verify", help="recalculate the workbook in LibreOffice and compare with Python")
    sp.add_argument("--out", type=Path, default=Path("outputs"))
    sp = sub.add_parser("send", help="send drafted reminders by SMTP (DRY RUN unless --send)")
    sp.add_argument("--outbox", type=Path, default=Path("outputs/reminders"))
    sp.add_argument("--send", action="store_true", help="actually send (default is a dry run)")
    sp.add_argument("--smtp-host")
    sp.add_argument("--smtp-port", type=int, default=587)
    sp.add_argument("--smtp-user")
    args = p.parse_args(argv)

    if args.cmd == "verify":
        from cvtrack.verify import compare

        res = run(DEFAULT_DATA, args.out, png=False)
        bad = compare(res, res["xlsx"])
        for b in bad:
            print(b)
        n = len(res["contracts"]) * 6 + len(res["invoices"]) * 3 + len(res["audit"]) * 5
        print(f"{'OK' if not bad else 'FAIL'}: {n} formula cells plus dashboard totals checked, {len(bad)} mismatch(es)")
        return 1 if bad else 0
    if args.cmd == "send":
        send_drafts(args.outbox, send=args.send, host=args.smtp_host, port=args.smtp_port, user=args.smtp_user)
        return 0
    as_of = None
    if args.as_of:
        as_of = date.today() if args.as_of == "today" else date.fromisoformat(args.as_of)
    try:
        res = run(args.data, args.out, args.config, as_of)
    except (InputError, ValueError) as e:
        print(f"error: {e}")
        return 2
    _print_report(res, args.out)
    return 0
