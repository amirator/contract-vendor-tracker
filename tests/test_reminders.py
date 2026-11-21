from email import policy
from email.parser import BytesParser

from conftest import audit_req, contract, invoice
from cvtrack.audit import evaluate_requests
from cvtrack.contracts import evaluate_contracts
from cvtrack.invoices import evaluate_invoices
from cvtrack.reminders import (audit_reminders, build_message, contract_reminders, invoice_reminders, render_html,
                               write_drafts)


def parse(path):
    return BytesParser(policy=policy.default).parsebytes(path.read_bytes())


def test_contract_digest_groups_by_owner_and_escalates_red(cfg):
    rows = [contract(contract_id="A", end_date="2026-11-30"), contract(contract_id="B", end_date="2027-01-30"),
            contract(contract_id="C", end_date="2026-12-01", owner="Other Person", owner_email="o.p@x.example"),
            contract(contract_id="D", end_date="2026-12-01", renewal_decision="Renew"),
            contract(contract_id="E", end_date="2028-01-01")]
    rem = contract_reminders(evaluate_contracts(rows, cfg), cfg)
    by_to = {r.to_email: r for r in rem}
    assert set(by_to) == {"owner@x.example", "o.p@x.example"}
    assert by_to["owner@x.example"].item_ids == ["A", "B"]  # D is decided, E is not in any band
    assert by_to["owner@x.example"].cc == [cfg.escalation_email]
    assert "2 contracts need a decision (1 urgent)" in by_to["owner@x.example"].subject


def test_invoice_recipients_by_status(cfg):
    vendors = {"V001": {"vendor_id": "V001", "contact_name": "Vee Endor", "contact_email": "accounts@vendor.example"}}
    rows = [invoice(invoice_id="I1", due_date="2026-11-20"),
            invoice(invoice_id="I2", due_date="2026-11-20", status="Approved - awaiting payment"),
            invoice(invoice_id="I3", due_date="2026-11-20", status="Awaiting vendor documents"),
            invoice(invoice_id="I4", due_date="2026-11-20", status="Disputed"),
            invoice(invoice_id="I5", due_date="2026-10-01")]
    rem = {r.kind: r for r in invoice_reminders(evaluate_invoices(rows, cfg), cfg, vendors)}
    assert rem["invoice-approver"].item_ids == ["I5", "I1"]  # most overdue first
    assert rem["invoice-approver"].cc == [cfg.escalation_email]  # I5 is > 30 days overdue
    assert rem["invoice-ap"].to_email == cfg.finance_ap_email and rem["invoice-ap"].greeting == "Dear colleagues,"
    assert rem["invoice-vendor"].to_email == "accounts@vendor.example" and rem["invoice-vendor"].cc == []
    assert all("I4" not in r.item_ids for r in rem.values())  # disputed: manual only


def test_audit_reminders_only_due_soon_and_overdue(cfg):
    rows = [audit_req(request_id="R1", due_date="2026-11-10"), audit_req(request_id="R2", due_date="2026-11-24"),
            audit_req(request_id="R3", due_date="2026-12-20")]
    (r,) = audit_reminders(evaluate_requests(rows, cfg), cfg)
    assert r.item_ids == ["R1", "R2"] and r.cc == [cfg.escalation_email]
    assert r.subject == "Audit requests: 1 overdue, 1 due within 3 working days"


def test_message_headers_and_parts(cfg):
    (r,) = audit_reminders(evaluate_requests([audit_req(due_date="2026-11-10")], cfg), cfg)
    msg = build_message(r, cfg)
    assert msg["Subject"].startswith("[SAMPLE] ")
    assert msg["X-Unsent"] == "1" and msg["X-Sample-Data"] == "true"
    assert "08:00:00 +0300" in msg["Date"]
    types = [p.get_content_type() for p in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]
    assert "SAMPLE / DEMO DATA" in msg.get_body("plain").get_content()


def test_html_is_escaped(cfg):
    (r,) = audit_reminders(evaluate_requests([audit_req(due_date="2026-11-10", item="<script>x</script>")], cfg), cfg)
    out = render_html(r, cfg)
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_write_drafts_replaces_old_files(cfg, tmp_path):
    (tmp_path / "stale.eml").write_text("old")
    (r,) = audit_reminders(evaluate_requests([audit_req(due_date="2026-11-10")], cfg), cfg)
    manifest = write_drafts([r], cfg, tmp_path)
    assert not (tmp_path / "stale.eml").exists()
    eml = tmp_path / manifest[0]["file"]
    assert parse(eml)["To"] == "Own Er <own.er@x.example>"
    assert (tmp_path / "outbox.csv").read_text().count("\n") == 2


def test_demo_drafts_parse_and_use_reserved_domains(demo):
    res, out = demo
    files = sorted((out / "reminders").glob("*.eml"))
    assert len(files) == len(res["manifest"]) > 0
    for f in files:
        msg = parse(f)
        for h in ("To", "Cc"):
            for addr in (msg[h] or "").split(","):
                if addr.strip():
                    assert addr.strip().rstrip(">").endswith(".example"), addr
