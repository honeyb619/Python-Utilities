from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from merge_pdfs import merge_pdfs


def _create_pdf(path: Path, pages: int = 1) -> None:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=72, height=72)
    with open(path, "wb") as f:
        w.write(f)


def test_merge(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    out = tmp_path / "out.pdf"
    _create_pdf(a, pages=1)
    _create_pdf(b, pages=2)
    merge_pdfs([str(a), str(b)], str(out))
    r = PdfReader(str(out))
    assert len(r.pages) == 3
