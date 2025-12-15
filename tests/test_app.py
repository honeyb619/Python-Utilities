import io

from PyPDF2 import PdfWriter


def _make_pdf_bytes(width=100, height=100):
    w = PdfWriter()
    w.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf


def test_merge_endpoint(client):
    a = _make_pdf_bytes(100, 110)
    b = _make_pdf_bytes(120, 130)

    data = {
        "files": [(a, "a.pdf"), (b, "b.pdf")]
    }
    resp = client.post("/merge", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/pdf")


def test_index_contains_ui_elements(client):
    resp = client.get('/')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'id="files-input"' in text
    assert 'id="selected-files"' in text
    assert 'id="selected-preview"' in text
    assert 'id="merged-preview"' in text
    # ensure new stylesheet and modern header exist
    assert 'static/style.css' in text
    assert 'Merge PDFs' in text


def test_per_file_resize(client):
    # first PDF will be resized to 8.5inx11in (612x792 pts), second preserved
    a = _make_pdf_bytes(100, 110)
    b = _make_pdf_bytes(120, 130)

    data = {
        'files': [(a, 'a.pdf'), (b, 'b.pdf')],
        'file_resize': ['8.5inx11in', 'preserve'],
    }
    resp = client.post('/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    from PyPDF2 import PdfReader
    r = PdfReader(io.BytesIO(resp.get_data()))
    assert len(r.pages) == 2
    w1 = float(r.pages[0].mediabox.width)
    h1 = float(r.pages[0].mediabox.height)
    # approx 612x792 pts
    assert abs(w1 - 612) < 1
    assert abs(h1 - 792) < 1


def test_per_file_resize_a4(client):
    a = _make_pdf_bytes(100, 110)
    b = _make_pdf_bytes(120, 130)

    data = {
        'files': [(a, 'a.pdf'), (b, 'b.pdf')],
        'file_resize': ['A4', 'preserve'],
    }
    resp = client.post('/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    from PyPDF2 import PdfReader
    import io
    r = PdfReader(io.BytesIO(resp.get_data()))
    assert len(r.pages) == 2
    w1 = float(r.pages[0].mediabox.width)
    h1 = float(r.pages[0].mediabox.height)
    # A4 in points ~ 595.28 x 841.89
    assert abs(w1 - 595.28) < 1.0
    assert abs(h1 - 841.89) < 1.0


def test_merge_respects_order(client):
    # create two PDFs with different page sizes and post them in reverse order
    a = _make_pdf_bytes(200, 300)
    b = _make_pdf_bytes(400, 500)

    data = {
        'files': [(b, 'b.pdf'), (a, 'a.pdf')],
    }
    resp = client.post('/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    from PyPDF2 import PdfReader
    import io
    r = PdfReader(io.BytesIO(resp.get_data()))
    assert len(r.pages) == 2
    w1 = float(r.pages[0].mediabox.width)
    h1 = float(r.pages[0].mediabox.height)
    assert abs(w1 - 400) < 1
    assert abs(h1 - 500) < 1
