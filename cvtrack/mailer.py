"""Optional SMTP sender for the drafted reminders. DRY RUN BY DEFAULT.

Without --send it only lists what would be sent. With --send it still refuses to send anything
addressed to a reserved test domain (.example, .test, .invalid, .localhost), so the bundled sample
drafts can never leave the machine. The password is read from the CVTRACK_SMTP_PASSWORD environment
variable and is never written to disk or printed.
"""

from __future__ import annotations

import os
import smtplib
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path

RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")


def recipients(msg) -> list[str]:
    return [a for _, a in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []))]


def is_reserved(addr: str) -> bool:
    return addr.lower().rstrip(">").endswith(RESERVED_TLDS)


def load_drafts(outbox: Path):
    return [(p, BytesParser(policy=policy.default).parsebytes(p.read_bytes())) for p in sorted(outbox.glob("*.eml"))]


def send_drafts(outbox: Path, *, send: bool = False, host: str | None = None, port: int = 587,
                user: str | None = None, smtp_factory=smtplib.SMTP, log=print) -> dict:
    drafts = load_drafts(outbox)
    result = {"drafts": len(drafts), "sent": 0, "skipped_reserved": 0, "dry_run": not send}
    if not send:
        for p, msg in drafts:
            log(f"DRY RUN  would send {p.name}: to {', '.join(recipients(msg))} | {msg['Subject']}")
        log(f"DRY RUN  {len(drafts)} draft(s); nothing was sent. Add --send (and SMTP settings) to send for real.")
        return result
    if not host:
        raise SystemExit("--send needs --smtp-host")
    sendable = []
    for p, msg in drafts:
        if any(is_reserved(a) for a in recipients(msg)):
            result["skipped_reserved"] += 1
            log(f"SKIPPED  {p.name}: addressed to a reserved test domain (sample data)")
        else:
            sendable.append((p, msg))
    if not sendable:
        log("Nothing to send.")
        return result
    password = os.environ.get("CVTRACK_SMTP_PASSWORD")
    with smtp_factory(host, port) as smtp:
        smtp.starttls()
        if user:
            if not password:
                raise SystemExit("set CVTRACK_SMTP_PASSWORD in the environment")
            smtp.login(user, password)
        for p, msg in sendable:
            del msg["X-Unsent"]
            smtp.send_message(msg)
            result["sent"] += 1
            log(f"SENT     {p.name}")
    return result
