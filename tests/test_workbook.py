import pytest
from openpyxl import load_workbook

from cvtrack.workbook import CONTRACT_COLS, CONTRACT_FORMULAS, FIRST, HEADER_ROW


@pytest.fixture(scope="module")
def wb(demo):
    res, out = demo
    return load_workbook(res["xlsx"]), res


def test_sheets_names_and_tables(wb):
    book, _ = wb
    assert book.sheetnames == ["Dashboard", "Settings", "Contracts", "Invoices", "Audit requests"]
    for name in ("AsOf", "Band1", "Band2", "Band3", "Age1", "ChaseGap", "Weekend"):
        assert name in book.defined_names
    assert set(book["Contracts"].tables) == {"tblContracts"}
    assert set(book["Invoices"].tables) == {"tblInvoices"}
    assert set(book["Audit requests"].tables) == {"tblAudit"}


def test_every_sheet_has_banner(wb):
    book, _ = wb
    for ws in book.worksheets:
        assert ws["A1"].value.startswith("SAMPLE / DEMO DATA"), ws.title


def test_formula_columns_are_live(wb):
    book, res = wb
    ws = book["Contracts"]
    for col in CONTRACT_FORMULAS:
        for r in range(FIRST, FIRST + len(res["contracts"])):
            assert str(ws[f"{col}{r}"].value).startswith("="), f"{col}{r}"
    assert ws[f"A{HEADER_ROW}"].value == CONTRACT_COLS[0][0]
    assert book["Settings"]["B5"].value.date().isoformat() == "2026-11-22"
    assert book["Dashboard"]["A6"].value.startswith("=COUNTIF(")


def test_formatting_validation_and_print(wb):
    book, _ = wb
    ws = book["Contracts"]
    assert ws.freeze_panes == f"B{FIRST}"
    assert len(ws.conditional_formatting) >= 3
    lists = {dv.formula1 for dv in ws.data_validations.dataValidation}
    assert '"Pending,Renew,Re-tender,Terminate"' in lists
    assert ws.page_setup.orientation == "landscape"
    assert book["Dashboard"]._charts and len(book["Dashboard"]._charts) == 2


def test_input_values_round_trip(wb):
    book, res = wb
    ws = book["Invoices"]
    total = sum(ws[f"G{r}"].value for r in range(FIRST, FIRST + len(res["invoices"])))
    assert total == pytest.approx(sum(float(s.row["amount_sar"]) for s in res["invoices"]))
