import io
import time
import sys
import urllib.request
import uuid

from PyPDF2 import PdfWriter


def make_pdf_bytes(width=100, height=100):
    w = PdfWriter()
    w.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf


def encode_multipart(fields, files):
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    crlf = '\r\n'
    body = io.BytesIO()
    for (name, value) in fields:
        body.write(('--' + boundary + crlf).encode())
        body.write((f'Content-Disposition: form-data; name="{name}"' + crlf + crlf).encode())
        body.write((str(value) + crlf).encode())
    for (name, filename, content, content_type) in files:
        body.write(('--' + boundary + crlf).encode())
        body.write((f'Content-Disposition: form-data; name="{name}"; filename="{filename}"' + crlf).encode())
        body.write((f'Content-Type: {content_type}' + crlf + crlf).encode())
        body.write(content.read())
        body.write(crlf.encode())
        content.seek(0)
    body.write(('--' + boundary + '--' + crlf).encode())
    body.seek(0)
    content_type = 'multipart/form-data; boundary=' + boundary
    return content_type, body.read()


def main():
    url = 'http://127.0.0.1:5000/merge'

    # wait for server
    for i in range(10):
        try:
            with urllib.request.urlopen('http://127.0.0.1:5000/') as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        print('Server not responding on http://127.0.0.1:5000/')
        sys.exit(1)

    a = make_pdf_bytes(100, 110)
    b = make_pdf_bytes(120, 130)

    files = [
        ('files', 'a.pdf', a, 'application/pdf'),
        ('files', 'b.pdf', b, 'application/pdf'),
    ]

    content_type, body = encode_multipart([], files)
    req = urllib.request.Request(url, data=body, headers={'Content-Type': content_type})
    try:
        with urllib.request.urlopen(req) as resp:
            out = resp.read()
            if resp.status != 200:
                print('Merge failed:', resp.status)
                print(out.decode('utf8', errors='ignore'))
                sys.exit(1)
            with open('Final_Invitation_Letter.pdf', 'wb') as f:
                f.write(out)
            print('Saved merged PDF to Final_Invitation_Letter.pdf')
    except urllib.error.HTTPError as e:
        print('HTTP error', e.code)
        print(e.read().decode('utf8', errors='ignore'))
        sys.exit(1)


if __name__ == '__main__':
    main()
