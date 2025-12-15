import io
import time
import sys

import requests
from PyPDF2 import PdfWriter


def make_pdf_bytes(width=100, height=100):
    w = PdfWriter()
    w.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf


def main():
    url = "http://127.0.0.1:5000/merge"

    # wait for server to be available
    for i in range(10):
        try:
            r = requests.get("http://127.0.0.1:5000/")
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        print("Server not responding on http://127.0.0.1:5000/")
        sys.exit(1)

    a = make_pdf_bytes(100, 110)
    b = make_pdf_bytes(120, 130)

    files = {
        'files': ('a.pdf', a, 'application/pdf'),
    }
    # requests supports multiple fields with same name via list of tuples
    multipart = [
        ('files', ('a.pdf', a, 'application/pdf')),
        ('files', ('b.pdf', b, 'application/pdf')),
    ]

    print('Uploading PDFs and requesting merge...')
    resp = requests.post(url, files=multipart)
    if resp.status_code != 200:
        print('Merge failed:', resp.status_code, resp.text)
        sys.exit(1)

    out_path = 'Final_Invitation_Letter.pdf'
    with open(out_path, 'wb') as f:
        f.write(resp.content)

    print('Saved merged PDF to', out_path)


if __name__ == '__main__':
    main()
