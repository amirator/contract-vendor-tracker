"""Weekly summary: plain-English paragraph, Markdown report and a one-page PNG control sheet."""

from __future__ import annotations

from pathlib import Path

from cvtrack.config import Config


def summary_text(cs: dict, inv: dict, au: dict, cfg: Config) -> str:
    last = cfg.contract_bands[-1]
    worst_bucket = next((b for b in reversed(list(inv["ageing_amount"])) if inv["ageing_amount"][b] > 0), None)
    rate = f"{au['on_time_rate']:.0%}" if au["on_time_rate"] is not None else "n/a"
    return (
        f"Contracts: {cs['by_rag']['Red']} of {cs['active']} active contracts are Red. "
        f"{cs['by_band']['Expired']} have already ended, {cs['undecided_in_window']} end within {last} days or have "
        f"ended with no renewal decision, and {cs['notice_missed']} have passed their notice deadline "
        f"({cfg.currency} {cs['value_expiring_window']:,.0f} of annual value ends in the next {last} days). "
        f"Invoices: {inv['open_count']} unpaid ({cfg.currency} {inv['open_amount']:,.0f}), of which "
        f"{inv['overdue_count']} are overdue ({cfg.currency} {inv['overdue_amount']:,.0f}); the oldest bucket with a "
        f"balance is {worst_bucket} days. {inv['actions']['Escalate']} invoices need escalation and "
        f"{inv['actions']['1st reminder'] + inv['actions']['2nd reminder'] + inv['actions']['Due-soon nudge']} need a "
        f"routine chaser. Audit: {au['open']} requests open, {au['overdue']} overdue and {au['due_soon']} due within "
        f"{cfg.audit_due_soon_business_days} working days; {rate} of submitted items were on time."
    )


def markdown_report(cs: dict, inv: dict, au: dict, manifest: list[dict], cfg: Config) -> str:
    cur = cfg.currency
    out = [f"# Contract and vendor control sheet - {cfg.company}", ""]
    if cfg.sample_data:
        out += ["> SAMPLE / DEMO DATA: fictional company, vendors and people.", ""]
    out += [f"As of {cfg.as_of:%d %b %Y}.", "", summary_text(cs, inv, au, cfg), "",
            "## Contracts by alert band", "", "| Band | Contracts |", "|---|---:|"]
    out += [f"| {b} | {n} |" for b, n in cs["by_band"].items()]
    out += ["", "## Unpaid invoices by days past due", "", f"| Bucket | Invoices | Amount ({cur}) |", "|---|---:|---:|"]
    out += [f"| {b} | {inv['ageing_count'][b]} | {inv['ageing_amount'][b]:,.2f} |" for b in inv["ageing_amount"]]
    out += [f"| **Total** | **{inv['open_count']}** | **{inv['open_amount']:,.2f}** |", "",
            "## Audit requests by owner", "", "| Owner | Open | Overdue |", "|---|---:|---:|"]
    out += [f"| {o} | {v['open']} | {v['overdue']} |" for o, v in au["by_owner"].items()]
    out += ["", f"## Reminder drafts ({len(manifest)}, not sent)", "", "| File | To | Cc | Subject |", "|---|---|---|---|"]
    out += [f"| {m['file']} | {m['to']} | {m['cc'] or '-'} | {m['subject']} |" for m in manifest]
    return "\n".join(out) + "\n"


def control_sheet_png(cs: dict, inv: dict, au: dict, cfg: Config, path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    navy, red, amber, green, grey = "#1F2A44", "#C0392B", "#D68910", "#1E8449", "#5D6D7E"
    fig = plt.figure(figsize=(12, 6.6), dpi=120)
    fig.patch.set_facecolor("white")
    fig.text(0.03, 0.95, f"Contract and vendor control sheet - {cfg.company}", fontsize=16, weight="bold", color=navy)
    fig.text(0.03, 0.915, f"As of {cfg.as_of:%d %b %Y}" + ("   |   SAMPLE / DEMO DATA (fictional)" if cfg.sample_data else ""),
             fontsize=10, color=grey)
    tiles = [
        ("Red contracts", f"{cs['by_rag']['Red']} / {cs['active']}", red),
        ("Notice deadline missed", str(cs["notice_missed"]), red),
        (f"Value ending in {cfg.contract_bands[-1]} d", f"{cfg.currency} {cs['value_expiring_window'] / 1e6:.2f}m", navy),
        ("Overdue invoices", f"{cfg.currency} {inv['overdue_amount'] / 1e3:,.0f}k", red),
        ("Audit items overdue", f"{au['overdue']} / {au['open']} open", amber),
    ]
    for k, (label, value, colour) in enumerate(tiles):
        x = 0.03 + k * 0.193
        fig.patches.append(matplotlib.patches.FancyBboxPatch((x, 0.75), 0.178, 0.13, boxstyle="round,pad=0.004",
                                                             transform=fig.transFigure, fc="#F4F6F8", ec="#D5D8DC"))
        fig.text(x + 0.01, 0.85, label, fontsize=9, color=grey)
        fig.text(x + 0.01, 0.775, value, fontsize=17, weight="bold", color=colour)

    ax1 = fig.add_axes([0.05, 0.12, 0.27, 0.52])
    bands = list(cs["by_band"])
    colours = [red, red, amber, amber, green]
    ax1.bar(bands, [cs["by_band"][b] for b in bands], color=colours)
    ax1.set_title("Active contracts by alert band", loc="left", fontsize=11, color=navy, weight="bold")
    for i, b in enumerate(bands):
        ax1.text(i, cs["by_band"][b] + 0.2, str(cs["by_band"][b]), ha="center", fontsize=9)

    ax2 = fig.add_axes([0.39, 0.12, 0.27, 0.52])
    buckets = list(inv["ageing_amount"])
    ax2.bar(buckets, [inv["ageing_amount"][b] / 1e3 for b in buckets], color=[green, amber, amber, red, red])
    ax2.set_title(f"Unpaid invoices by days past due ({cfg.currency} k)", loc="left", fontsize=11, color=navy, weight="bold")
    for i, b in enumerate(buckets):
        ax2.text(i, inv["ageing_amount"][b] / 1e3 + 2, f"{inv['ageing_amount'][b] / 1e3:,.0f}", ha="center", fontsize=9)

    ax3 = fig.add_axes([0.75, 0.12, 0.22, 0.52])
    owners = [o for o, v in au["by_owner"].items() if v["open"]]
    owners.sort(key=lambda o: au["by_owner"][o]["open"])
    ov = [au["by_owner"][o]["overdue"] for o in owners]
    rest = [au["by_owner"][o]["open"] - au["by_owner"][o]["overdue"] for o in owners]
    ax3.barh(owners, ov, color=red, label="Overdue")
    ax3.barh(owners, rest, left=ov, color="#AEB6BF", label="Open, not overdue")
    ax3.set_title("Open audit requests by owner", loc="left", fontsize=11, color=navy, weight="bold")
    ax3.legend(fontsize=8, frameon=False, loc="lower right")
    from matplotlib.ticker import MaxNLocator

    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax3.xaxis.set_major_locator(MaxNLocator(integer=True))
    for ax in (ax1, ax2, ax3):
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8.5)
    fig.text(0.03, 0.03, "Rules: alert bands 90/60/30 days before contract end; ageing by days past payment due date; "
             "audit 'due soon' within working days (Fri-Sat weekend).", fontsize=8.5, color=grey)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path
