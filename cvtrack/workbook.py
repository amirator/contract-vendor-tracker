"""Build the Excel tracker: live formulas, named settings, conditional formatting, drop-downs, charts.

Python computes the same results (contracts.py, invoices.py, audit.py); the workbook keeps them live
so the office can keep using the file without Python. tests/test_workbook_recalc.py recalculates the
file in LibreOffice and checks every formula cell against the Python result.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule, DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from cvtrack.config import DAY_NAMES, Config
from cvtrack.dates import parse
from cvtrack.invoices import STATUSES as INVOICE_STATUSES

NAVY = "1F2A44"
FILL_RED, FILL_AMBER, FILL_GREEN = "F5B7B1", "FAD7A0", "ABEBC6"
FONT_RED, FONT_AMBER, FONT_GREEN = "922B21", "9A5B00", "186A3B"
BANNER = "SAMPLE / DEMO DATA - fictional company, vendors and people. Not real contracts or invoices."
DATE_FMT, MONEY_FMT = "dd-mmm-yyyy", "#,##0"
HEADER_ROW, FIRST = 4, 5  # table header row, first data row

CONTRACT_STATUSES = ["Active", "Under renewal", "Terminated"]
DECISIONS = ["Pending", "Renew", "Re-tender", "Terminate"]
AUDIT_STATUSES = ["Open", "In progress", "Submitted", "Closed"]
PRIORITIES = ["High", "Medium", "Low"]

thin = Side(style="thin", color="D5D8DC")


def _fill(hex_):
    return PatternFill("solid", start_color=hex_, end_color=hex_)


def _weekend_code(cfg: Config) -> str:
    return "".join("1" if d in cfg.weekend else "0" for d in DAY_NAMES)


SETTINGS = [  # (name, label, attr)
    ("Company", "Company", "company"),
    ("AsOf", "As-of date (replace with =TODAY() for live use)", "as_of"),
    ("Band1", "Contract alert band 1 (days)", ("contract_bands", 0)),
    ("Band2", "Contract alert band 2 (days)", ("contract_bands", 1)),
    ("Band3", "Contract alert band 3 (days)", ("contract_bands", 2)),
    ("NoticeWarn", "Warn when notice deadline is within (days)", "notice_warning_days"),
    ("Age1", "Invoice ageing edge 1 (days past due)", ("ageing_buckets", 0)),
    ("Age2", "Invoice ageing edge 2", ("ageing_buckets", 1)),
    ("Age3", "Invoice ageing edge 3", ("ageing_buckets", 2)),
    ("DueSoon", "Nudge approvers this many days before due", "due_soon_days"),
    ("ChaseGap", "Minimum days between chasers", "chase_gap_days"),
    ("EscDays", "Escalate invoices overdue more than (days)", "escalate_after_days_overdue"),
    ("EscChases", "Escalate after this many chasers", "escalate_after_chases"),
    ("AuditSoon", "Audit item 'due soon' within (working days)", "audit_due_soon_business_days"),
    ("AuditEsc", "Escalate audit items overdue more than (days)", "audit_escalate_days_overdue"),
    ("Weekend", "Weekend code for NETWORKDAYS.INTL (Mon..Sun, 1 = weekend)", None),
]

CONTRACT_COLS = [  # (header, source key or None for formula, width, format)
    ("Contract", "contract_id", 10, None), ("Title", "title", 34, None), ("Vendor", "vendor_name", 30, None),
    ("Category", "category", 18, None), ("Owner", "owner", 15, None), ("Department", "department", 16, None),
    ("Start", "start_date", 12, DATE_FMT), ("End", "end_date", 12, DATE_FMT), ("Notice days", "notice_days", 8, "0"),
    ("Auto-renew", "auto_renew", 8, None), ("Annual value", "annual_value_sar", 13, MONEY_FMT),
    ("Status", "status", 13, None), ("Decision", "renewal_decision", 11, None),
    ("Owner email", "owner_email", 30, None),
    ("Days to expiry", None, 9, "0"), ("Notice deadline", None, 12, DATE_FMT), ("Days to notice", None, 9, "0"),
    ("Band", None, 9, None), ("Notice flag", None, 24, None), ("RAG", None, 7, None),
]
CONTRACT_FORMULAS = {  # inputs A-N, formulas O-T
    "O": '=IF(L{r}="Terminated","",H{r}-AsOf)',
    "P": "=H{r}-I{r}",
    "Q": "=P{r}-AsOf",
    "R": '=IF(L{r}="Terminated","Closed",IF(O{r}<0,"Expired",IF(O{r}<=Band1,Band1&"-day",'
         'IF(O{r}<=Band2,Band2&"-day",IF(O{r}<=Band3,Band3&"-day","OK")))))',
    "S": '=IF(OR(L{r}="Terminated",M{r}<>"Pending",H{r}<AsOf),"",IF(Q{r}<0,IF(J{r}="Y",'
         '"Notice missed - auto-renews","Notice missed"),IF(Q{r}<=NoticeWarn,"Notice due","")))',
    "T": '=IF(L{r}="Terminated","",IF(AND(M{r}="Pending",OR(R{r}="Expired",R{r}=Band1&"-day",'
         'LEFT(S{r},13)="Notice missed")),"Red",IF(OR(R{r}<>"OK",S{r}="Notice due"),"Amber","Green")))',
}

INVOICE_COLS = [
    ("Invoice", "invoice_id", 11, None), ("Vendor", "vendor_name", 30, None), ("Contract", "contract_id", 9, None),
    ("PO", "po_number", 9, None), ("Invoice date", "invoice_date", 12, DATE_FMT), ("Due date", "due_date", 12, DATE_FMT),
    ("Amount (incl. VAT)", "amount_sar", 13, "#,##0.00"), ("Status", "status", 26, None), ("Approver", "approver", 15, None),
    ("Paid date", "paid_date", 12, DATE_FMT), ("Last chased", "last_chased", 12, DATE_FMT),
    ("Chasers sent", "chase_count", 8, "0"),
    ("Days past due", None, 9, "0"), ("Ageing bucket", None, 12, None), ("Days since chase", None, 9, "0"),
    ("Next action", None, 17, None),
]
INVOICE_FORMULAS = {
    "M": '=IF(H{r}="Paid","",AsOf-F{r})',
    "N": '=IF(H{r}="Paid","Paid",IF(M{r}<=0,"Not yet due",IF(M{r}<=Age1,"1-"&Age1,IF(M{r}<=Age2,(Age1+1)&"-"&Age2,'
         'IF(M{r}<=Age3,(Age2+1)&"-"&Age3,Age3&"+")))))',
    "O": '=IF(K{r}="","",AsOf-K{r})',
    "P": '=IF(H{r}="Paid","",IF(H{r}="Disputed","Manual follow-up",IF(AND(K{r}<>"",O{r}<ChaseGap),"Chased recently",'
         'IF(OR(AND(H{r}="Pending approval",M{r}>=-DueSoon),AND(H{r}="Approved - awaiting payment",M{r}>0),'
         'H{r}="Awaiting vendor documents"),IF(OR(M{r}>EscDays,L{r}>=EscChases),"Escalate",IF(L{r}=0,'
         'IF(M{r}<=0,"Due-soon nudge","1st reminder"),"2nd reminder")),""))))',
}

AUDIT_COLS = [
    ("Request", "request_id", 9, None), ("Audit", "audit", 30, None), ("Requested by", "requested_by", 26, None),
    ("Item", "item", 40, None), ("Owner", "owner", 15, None), ("Department", "department", 16, None),
    ("Priority", "priority", 9, None), ("Requested", "requested_date", 12, DATE_FMT), ("Due", "due_date", 12, DATE_FMT),
    ("Status", "status", 11, None), ("Submitted", "submitted_date", 12, DATE_FMT),
    ("Days open", None, 8, "0"), ("Working days to due", None, 10, "0"), ("Days overdue", None, 9, "0"),
    ("State", None, 17, None), ("Escalate", None, 9, None),
]
AUDIT_FORMULAS = {
    "L": '=IF(OR(J{r}="Submitted",J{r}="Closed"),K{r}-H{r},AsOf-H{r})',
    "M": "=IF(I{r}=AsOf,0,IF(I{r}>AsOf,NETWORKDAYS.INTL(AsOf+1,I{r},Weekend),"
         "-NETWORKDAYS.INTL(I{r},AsOf-1,Weekend)))",
    "N": '=IF(OR(J{r}="Submitted",J{r}="Closed"),0,MAX(AsOf-I{r},0))',
    "O": '=IF(OR(J{r}="Submitted",J{r}="Closed"),IF(K{r}<=I{r},"Submitted on time","Submitted late"),'
         'IF(I{r}<AsOf,"Overdue",IF(M{r}<=AuditSoon,"Due soon","On track")))',
    "P": '=IF(AND(O{r}="Overdue",N{r}>AuditEsc),"Yes","")',
}


def _value(key: str, raw: str, fmt):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if fmt == DATE_FMT:
        return parse(raw)
    if fmt in (MONEY_FMT, "#,##0.00"):
        return float(raw)
    if fmt == "0":
        return int(raw)
    return raw


def _banner(ws, title: str, ncols: int):
    ws["A1"] = BANNER
    ws["A1"].font = Font(bold=True, color="7D6608")
    ws["A1"].fill = _fill("FFF4CE")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=min(ncols, 12))
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=14, color=NAVY)


def _sheet(wb, name, title, cols, formulas, rows, table_name):
    ws = wb.create_sheet(name)
    _banner(ws, title, len(cols))
    ws["A3"] = "Grey columns are inputs; navy-header columns on the right are formulas. Edit inputs only."
    ws["A3"].font = Font(italic=True, color="5D6D7E", size=9)
    for j, (head, key, width, _) in enumerate(cols, start=1):
        c = ws.cell(HEADER_ROW, j, head)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _fill(NAVY if key is None else "566573")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.row_dimensions[HEADER_ROW].height = 32
    for i, row in enumerate(rows):
        r = FIRST + i
        for j, (_, key, _, fmt) in enumerate(cols, start=1):
            col = get_column_letter(j)
            cell = ws.cell(r, j)
            cell.value = formulas[col].format(r=r) if key is None else _value(key, row.get(key, ""), fmt)
            if fmt:
                cell.number_format = fmt
            cell.border = Border(bottom=thin)
    last = FIRST + len(rows) - 1
    ref = f"A{HEADER_ROW}:{get_column_letter(len(cols))}{last}"
    t = Table(displayName=table_name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes = ws.cell(FIRST, 2)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    return ws, last


def _rag_rules(ws, rng, red, amber, green=None):
    for text, fill, font in ((red, FILL_RED, FONT_RED), (amber, FILL_AMBER, FONT_AMBER), (green, FILL_GREEN, FONT_GREEN)):
        if text is None:
            continue
        for t in ([text] if isinstance(text, str) else text):
            ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{t}"'], fill=_fill(fill),
                                                          font=Font(color=font, bold=True)))


def _validation(ws, col, last, options):
    dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
    dv.error, dv.errorTitle = "Pick a value from the list", "Invalid entry"
    ws.add_data_validation(dv)
    dv.add(f"{col}{FIRST}:{col}{last + 200}")


def build_workbook(data: dict[str, list[dict]], cfg: Config, summary_text: str, path: Path) -> Path:
    if len(cfg.contract_bands) != 3 or len(cfg.ageing_buckets) != 3:
        raise ValueError("the Excel workbook supports exactly 3 contract bands and 3 ageing edges")
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True  # Excel recalculates every formula when the file opens
    dash = wb.active
    dash.title = "Dashboard"

    # Settings (named cells drive every formula)
    st = wb.create_sheet("Settings")
    _banner(st, "Settings - every threshold used by the formulas", 3)
    st.column_dimensions["A"].width, st.column_dimensions["B"].width, st.column_dimensions["C"].width = 52, 16, 12
    for i, (name, label, attr) in enumerate(SETTINGS, start=4):
        st.cell(i, 1, label)
        if attr is None:
            v = _weekend_code(cfg)
        elif isinstance(attr, tuple):
            v = getattr(cfg, attr[0])[attr[1]]
        else:
            v = getattr(cfg, attr)
        c = st.cell(i, 2, v)
        c.fill = _fill("EAF2F8")
        if isinstance(v, date):
            c.number_format = DATE_FMT
        st.cell(i, 3, name).font = Font(color="5D6D7E", italic=True)
        wb.defined_names[name] = DefinedName(name, attr_text=f"Settings!$B${i}")

    c_ws, c_last = _sheet(wb, "Contracts", "Contract register - renewal and expiry alerts", CONTRACT_COLS,
                          CONTRACT_FORMULAS, data["contracts"], "tblContracts")
    i_ws, i_last = _sheet(wb, "Invoices", "Vendor-invoice follow-up - ageing and chasers", INVOICE_COLS,
                          INVOICE_FORMULAS, data["invoices"], "tblInvoices")
    a_ws, a_last = _sheet(wb, "Audit requests", "Audit-request log - owners, due dates, status", AUDIT_COLS,
                          AUDIT_FORMULAS, data["audit_requests"], "tblAudit")

    # conditional formatting and drop-downs
    _rag_rules(c_ws, f"T{FIRST}:T{c_last}", "Red", "Amber", "Green")
    _rag_rules(c_ws, f"R{FIRST}:R{c_last}", ["Expired", f"{cfg.contract_bands[0]}-day"],
               [f"{cfg.contract_bands[1]}-day", f"{cfg.contract_bands[2]}-day"])
    c_ws.conditional_formatting.add(f"S{FIRST}:S{c_last}", FormulaRule(
        formula=[f'LEFT(S{FIRST},13)="Notice missed"'], font=Font(color=FONT_RED, bold=True)))
    c_ws.conditional_formatting.add(f"K{FIRST}:K{c_last}", DataBarRule(start_type="num", start_value=0,
                                                                       end_type="max", color="85A9D6"))
    _validation(c_ws, "J", c_last, ["Y", "N"])
    _validation(c_ws, "L", c_last, CONTRACT_STATUSES)
    _validation(c_ws, "M", c_last, DECISIONS)

    _rag_rules(i_ws, f"P{FIRST}:P{i_last}", ["Escalate"], ["2nd reminder", "1st reminder", "Manual follow-up"])
    _rag_rules(i_ws, f"N{FIRST}:N{i_last}", [f"{cfg.ageing_buckets[2]}+", f"{cfg.ageing_buckets[1] + 1}-{cfg.ageing_buckets[2]}"],
               [f"{cfg.ageing_buckets[0] + 1}-{cfg.ageing_buckets[1]}"])
    i_ws.conditional_formatting.add(f"A{FIRST}:P{i_last}", FormulaRule(
        formula=[f'$H{FIRST}="Paid"'], font=Font(color="99A3A4")))
    _validation(i_ws, "H", i_last, INVOICE_STATUSES)

    _rag_rules(a_ws, f"O{FIRST}:O{a_last}", ["Overdue", "Submitted late"], ["Due soon"], ["Submitted on time"])
    _rag_rules(a_ws, f"P{FIRST}:P{a_last}", "Yes", None)
    _validation(a_ws, "J", a_last, AUDIT_STATUSES)
    _validation(a_ws, "G", a_last, PRIORITIES)

    _dashboard(dash, cfg, c_last, i_last, a_last, data, summary_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _tile(ws, cell, label, formula, fmt="0", colour=NAVY):
    col, row = cell[0], int(cell[1:])
    ws[f"{col}{row}"] = label
    ws[f"{col}{row}"].font = Font(size=9, color="5D6D7E")
    ws[f"{col}{row}"].alignment = Alignment(wrap_text=True, vertical="bottom")
    ws[f"{col}{row + 1}"] = formula
    ws[f"{col}{row + 1}"].font = Font(size=18, bold=True, color=colour)
    ws[f"{col}{row + 1}"].number_format = fmt


def _dashboard(ws, cfg, c_last, i_last, a_last, data, summary_text):
    _banner(ws, f"Contract and vendor control sheet - {cfg.company}", 10)
    ws["A3"] = "As of"
    ws["B3"] = "=AsOf"
    ws["B3"].number_format = DATE_FMT
    ws["B3"].font = Font(bold=True)
    for col, w in zip("ABCDEFGHIJ", (24, 14, 14, 16, 3, 30, 14, 14, 16, 3)):
        ws.column_dimensions[col].width = w
    ws.row_dimensions[5].height = 26
    C = lambda col: f"Contracts!${col}${FIRST}:${col}${c_last}"
    I = lambda col: f"Invoices!${col}${FIRST}:${col}${i_last}"
    A = lambda col: f"'Audit requests'!${col}${FIRST}:${col}${a_last}"

    _tile(ws, "A5", "Active contracts", f'=COUNTIF({C("L")},"<>Terminated")')
    _tile(ws, "B5", "Red contracts", f'=COUNTIF({C("T")},"Red")', colour="C0392B")
    _tile(ws, "C5", "Notice missed", f'=COUNTIF({C("S")},"Notice missed*")', colour="C0392B")
    _tile(ws, "D5", f"Annual value ending in {cfg.contract_bands[-1]} days",
          f'=SUMIFS({C("K")},{C("O")},">=0",{C("O")},"<="&Band3)', MONEY_FMT)
    _tile(ws, "F5", "Unpaid invoices (SAR)", f'=SUMIFS({I("G")},{I("H")},"<>Paid")', MONEY_FMT)
    _tile(ws, "G5", "Overdue (SAR)", f'=SUMIFS({I("G")},{I("H")},"<>Paid",{I("M")},">0")', MONEY_FMT, "C0392B")
    _tile(ws, "H5", "Open audit items", f'=COUNTIF({A("J")},"Open")+COUNTIF({A("J")},"In progress")')
    _tile(ws, "I5", "Audit items overdue", f'=COUNTIF({A("O")},"Overdue")', colour="C0392B")

    hdr = lambda cell, text: (ws.__setitem__(cell, text), setattr(ws[cell], "font", Font(bold=True, color="FFFFFF")),
                              setattr(ws[cell], "fill", _fill(NAVY)))
    # contracts by band
    ws["A9"] = "Contracts by alert band"
    ws["A9"].font = Font(bold=True, color=NAVY, size=12)
    for cell, t in (("A10", "Band"), ("B10", "Contracts"), ("C10", "Annual value"), ("D10", "No decision yet")):
        hdr(cell, t)
    bands = ['"Expired"', 'Band1&"-day"', 'Band2&"-day"', 'Band3&"-day"', '"OK"']
    for k, b in enumerate(bands):
        r = 11 + k
        ws[f"A{r}"] = f"={b}"
        ws[f"B{r}"] = f"=COUNTIF({C('R')},A{r})"
        ws[f"C{r}"] = f"=SUMIFS({C('K')},{C('R')},A{r})"
        ws[f"C{r}"].number_format = MONEY_FMT
        ws[f"D{r}"] = f'=COUNTIFS({C("R")},A{r},{C("M")},"Pending")'
    _rag_rules(ws, "A11:A12", ["Expired", f"{cfg.contract_bands[0]}-day"], None)
    # invoice ageing
    ws["F9"] = "Unpaid invoices by ageing bucket"
    ws["F9"].font = Font(bold=True, color=NAVY, size=12)
    for cell, t in (("F10", "Days past due"), ("G10", "Invoices"), ("H10", "Amount (SAR)")):
        hdr(cell, t)
    labels = ['"Not yet due"', '"1-"&Age1', '(Age1+1)&"-"&Age2', '(Age2+1)&"-"&Age3', 'Age3&"+"']
    for k, lab in enumerate(labels):
        r = 11 + k
        ws[f"F{r}"] = f"={lab}"
        ws[f"G{r}"] = f"=COUNTIF({I('N')},F{r})"
        ws[f"H{r}"] = f"=SUMIFS({I('G')},{I('N')},F{r})"
        ws[f"H{r}"].number_format = MONEY_FMT
    ws["F16"], ws["G16"], ws["H16"] = "Total unpaid", "=SUM(G11:G15)", "=SUM(H11:H15)"
    ws["H16"].number_format = MONEY_FMT
    for c in ("F16", "G16", "H16"):
        ws[c].font = Font(bold=True)
    # next actions
    ws["A18"] = "Invoice follow-up this week"
    ws["A18"].font = Font(bold=True, color=NAVY, size=12)
    hdr("A19", "Next action")
    hdr("B19", "Invoices")
    for k, act in enumerate(["Due-soon nudge", "1st reminder", "2nd reminder", "Escalate", "Chased recently",
                             "Manual follow-up"]):
        r = 20 + k
        ws[f"A{r}"] = act
        ws[f"B{r}"] = f"=COUNTIF({I('P')},A{r})"
    # audit by owner
    ws["F18"] = "Audit requests by owner"
    ws["F18"].font = Font(bold=True, color=NAVY, size=12)
    for cell, t in (("F19", "Owner"), ("G19", "Open"), ("H19", "Overdue"), ("I19", "Escalate")):
        hdr(cell, t)
    owners = sorted({r["owner"] for r in data["audit_requests"]})
    for k, o in enumerate(owners):
        r = 20 + k
        ws[f"F{r}"] = o
        ws[f"G{r}"] = f'=COUNTIFS({A("E")},F{r},{A("J")},"Open")+COUNTIFS({A("E")},F{r},{A("J")},"In progress")'
        ws[f"H{r}"] = f'=COUNTIFS({A("E")},F{r},{A("O")},"Overdue")'
        ws[f"I{r}"] = f'=COUNTIFS({A("E")},F{r},{A("P")},"Yes")'
    r = 20 + len(owners)
    ws[f"F{r}"] = "On-time submission rate"
    ws[f"F{r}"].font = Font(bold=True)
    ws[f"G{r}"] = (f'=IFERROR(COUNTIF({A("O")},"Submitted on time")/(COUNTIF({A("O")},"Submitted on time")'
                   f'+COUNTIF({A("O")},"Submitted late")),"")')
    ws[f"G{r}"].number_format = "0%"
    ws.conditional_formatting.add(f"H20:I{r - 1}", CellIsRule(operator="greaterThan", formula=["0"],
                                                              fill=_fill(FILL_RED), font=Font(color=FONT_RED, bold=True)))
    # written summary
    sr = max(r, 26) + 2
    ws[f"A{sr}"] = "Summary (written by the Python report for the as-of date above)"
    ws[f"A{sr}"].font = Font(bold=True, color=NAVY, size=12)
    ws[f"A{sr + 1}"] = summary_text
    ws[f"A{sr + 1}"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=sr + 1, start_column=1, end_row=sr + 1, end_column=9)
    ws.row_dimensions[sr + 1].height = 92
    # charts
    ch = BarChart()
    ch.type, ch.style, ch.title = "col", 10, "Unpaid invoices by days past due (SAR)"
    ch.add_data(Reference(ws, min_col=8, min_row=10, max_row=15), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=6, min_row=11, max_row=15))
    ch.legend, ch.height, ch.width = None, 7, 13
    ws.add_chart(ch, f"A{sr + 3}")
    ch2 = BarChart()
    ch2.type, ch2.style, ch2.title = "col", 10, "Contracts by alert band"
    ch2.add_data(Reference(ws, min_col=2, min_row=10, max_row=15), titles_from_data=True)
    ch2.set_categories(Reference(ws, min_col=1, min_row=11, max_row=15))
    ch2.legend, ch2.height, ch2.width = None, 7, 13
    ws.add_chart(ch2, f"F{sr + 3}")
    ws.page_setup.orientation, ws.page_setup.paperSize = "landscape", ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_view.showGridLines = False
