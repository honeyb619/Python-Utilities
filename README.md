# merge_pdfs

Small utility to merge PDF files using PyPDF2.

Usage:

```
python merge_pdfs.py file1.pdf file2.pdf -o merged.pdf
python merge_pdfs.py -o all.pdf  # merges all PDFs in current directory
```

Options:
- `-o, --output` : output filename (default `merged.pdf`)
- `-r, --recursive` : include PDFs in subdirectories
- `--page-size` : optional. If omitted, original page sizes are preserved. To resize, pass `largest`, `smallest`, `first` or `WIDTHxHEIGHT` (e.g. `8.5inx11in`).


Run tests:

```
pip install -r requirements.txt
python -m pytest -q
```

Run the web UI:

```
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000 in your browser

Templates are located under `webapp/templates/`.

The web UI now shows the list of selected files and provides in-browser previews for the selected PDF and the merged PDF.

UI improvements: cleaner layout, responsive preview panes and a polished stylesheet.
```
