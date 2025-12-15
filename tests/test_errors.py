from pathlib import Path

from importlib import reload
import merge_pdfs


def _main(args):
    reload(merge_pdfs)
    return merge_pdfs.main(args)


def test_unreadable_pdf(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.pdf"
    out = tmp_path / "out.pdf"
    bad.write_text("this is not a valid pdf file")

    rc = _main([str(bad), "-o", str(out)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "There was a problem reading the document" in captured.err
    assert not out.exists()
