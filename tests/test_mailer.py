import pytest

from conftest import audit_req
from cvtrack.audit import evaluate_requests
from cvtrack.mailer import is_reserved, send_drafts
from cvtrack.reminders import audit_reminders, write_drafts


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host, self.port, self.sent, self.logged_in = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        self.logged_in = (user, pw)

    def send_message(self, msg):
        self.sent.append(msg)


class ExplodingSMTP:
    def __init__(self, *a):
        raise AssertionError("SMTP must not be opened")


def drafts(cfg, tmp_path, email="own.er@x.example"):
    (r,) = audit_reminders(evaluate_requests([audit_req(due_date="2026-11-10", owner_email=email)], cfg), cfg)
    r.cc = []
    write_drafts([r], cfg, tmp_path)
    return tmp_path


def test_reserved_domains():
    assert is_reserved("a@b.example") and is_reserved("a@b.test") and not is_reserved("a@b.com")


def test_default_is_dry_run(cfg, tmp_path):
    lines = []
    res = send_drafts(drafts(cfg, tmp_path), smtp_factory=ExplodingSMTP, log=lines.append)
    assert res == {"drafts": 1, "sent": 0, "skipped_reserved": 0, "dry_run": True}
    assert lines[-1].startswith("DRY RUN")


def test_send_refuses_reserved_domains(cfg, tmp_path):
    res = send_drafts(drafts(cfg, tmp_path), send=True, host="smtp.local", smtp_factory=ExplodingSMTP, log=lambda m: None)
    assert res["sent"] == 0 and res["skipped_reserved"] == 1


def test_send_path_with_fake_server(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("CVTRACK_SMTP_PASSWORD", "pw")
    FakeSMTP.instances.clear()
    res = send_drafts(drafts(cfg, tmp_path, "real@company.com"), send=True, host="smtp.local", user="me",
                      smtp_factory=FakeSMTP, log=lambda m: None)
    (smtp,) = FakeSMTP.instances
    assert res["sent"] == 1 and smtp.logged_in == ("me", "pw")
    assert smtp.sent[0]["X-Unsent"] is None


def test_send_needs_host_and_password(cfg, tmp_path, monkeypatch):
    d = drafts(cfg, tmp_path, "real@company.com")
    with pytest.raises(SystemExit, match="smtp-host"):
        send_drafts(d, send=True, smtp_factory=FakeSMTP, log=lambda m: None)
    monkeypatch.delenv("CVTRACK_SMTP_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="CVTRACK_SMTP_PASSWORD"):
        send_drafts(d, send=True, host="h", user="me", smtp_factory=FakeSMTP, log=lambda m: None)
