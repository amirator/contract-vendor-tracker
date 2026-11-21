"""Render PNG screenshots of the real demo outputs into docs/ for the README.

Needs LibreOffice (soffice), poppler (pdftoppm) and Google Chrome/Chromium on PATH.
Run `python -m cvtrack demo` first.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
OUT, DOCS = ROOT / "outputs", ROOT / "docs"


def run(*cmd):
    subprocess.run(cmd, check=True, capture_output=True, timeout=240)


def autocrop(path: Path, pad: int = 20, bg: str = "white") -> None:
    im = Image.open(path).convert("RGB")
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, bg)).getbbox()
    if bbox:
        l, t, r, b = bbox
        im.crop((max(l - pad, 0), max(t - pad, 0), min(r + pad, im.width), min(b + pad, im.height))).save(path)


def sheet_png(xlsx: Path, sheet: str, dest: Path, rows: int | None = None, cols: str | None = None, dpi: int = 110,
              hide: str = ""):
    """Print one sheet (optionally a range) to PDF with LibreOffice and rasterise page 1."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = load_workbook(xlsx)
        for ws in wb.worksheets:
            if ws.title != sheet:
                ws.sheet_state = "hidden"
        ws = wb[sheet]
        wb.active = wb.worksheets.index(ws)
        for c in hide:
            ws.column_dimensions[c].hidden = True
        if rows and cols:
            ws.print_area = f"A1:{cols}{rows}"
        one = tmp / "one.xlsx"
        wb.save(one)
        profile = tmp / "profile"
        run(shutil.which("soffice"), f"-env:UserInstallation=file://{profile}", "--headless",
            "--convert-to", "pdf", "--outdir", str(tmp), str(one))
        run("pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile", str(tmp / "one.pdf"), str(tmp / "p"))
        shutil.move(tmp / "p.png", dest)
    autocrop(dest)


def html_png(html: Path, dest: Path, width: int = 1000, height: int = 760):
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    run(chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        f"--window-size={width},{height}", f"--screenshot={dest}", html.as_uri())
    autocrop(dest)


def main() -> int:
    xlsx = OUT / "contract_vendor_tracker.xlsx"
    if not xlsx.exists():
        print("run `python -m cvtrack demo` first")
        return 1
    DOCS.mkdir(exist_ok=True)
    shutil.copy(OUT / "control_sheet.png", DOCS / "control_sheet.png")
    sheet_png(xlsx, "Dashboard", DOCS / "excel_dashboard.png")
    sheet_png(xlsx, "Contracts", DOCS / "excel_contracts.png", rows=24, cols="T", hide="DFGN", dpi=130)
    sheet_png(xlsx, "Invoices", DOCS / "excel_invoices.png", rows=24, cols="P", hide="CDE", dpi=130)
    sheet_png(xlsx, "Audit requests", DOCS / "excel_audit.png", rows=24, cols="P", hide="CF", dpi=130)
    rem = OUT / "reminders"
    first = {}
    for f in sorted(rem.glob("*.html")):
        kind = f.name.split("_")[1]
        first.setdefault(kind, f)
    for kind, f in first.items():
        html_png(f, DOCS / f"email_{kind}.png")
    for p in sorted(DOCS.glob("*.png")):
        print(p.relative_to(ROOT), Image.open(p).size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
