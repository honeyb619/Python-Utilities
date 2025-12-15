from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from importlib import reload
import merge_pdfs


def _main(args):
    reload(merge_pdfs)
    return merge_pdfs.main(args)


def _create_pdf(path: Path, width: float, height: float) -> None:
    w = PdfWriter()
    w.add_blank_page(width=width, height=height)
    with open(path, "wb") as f:
        w.write(f)


def test_resize_to_largest(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    out = tmp_path / "out.pdf"
    # create PDFs with different sizes
    _create_pdf(a, width=200, height=300)
    _create_pdf(b, width=400, height=600)

    rc = _main([str(a), str(b), "-o", str(out), "--page-size", "largest"])
    assert rc == 0

    r = PdfReader(str(out))
    # all pages in the merged file should have the same size (largest)
    assert len(r.pages) == 2
    w0 = float(r.pages[0].mediabox.width)
    h0 = float(r.pages[0].mediabox.height)
    w1 = float(r.pages[1].mediabox.width)
    h1 = float(r.pages[1].mediabox.height)
    assert abs(w0 - w1) < 1e-6
    assert abs(h0 - h1) < 1e-6
    assert int(w0) == 400 and int(h0) == 600
