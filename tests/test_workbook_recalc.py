"""Excel formulas must give exactly the Python results (recalculated by LibreOffice)."""

import pytest

from cvtrack.verify import compare, soffice

pytestmark = pytest.mark.skipif(soffice() is None, reason="LibreOffice not installed")


def test_formulas_match_python(demo):
    res, _ = demo
    assert compare(res, res["xlsx"]) == []


def test_formulas_match_python_on_another_date(tmp_path):
    from datetime import date

    from conftest import SAMPLE
    from cvtrack.cli import run

    res = run(SAMPLE, tmp_path, as_of=date(2027, 2, 4), png=False)  # a Thursday, different bands
    assert compare(res, res["xlsx"]) == []
