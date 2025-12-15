from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List

from flask import Flask, Response, flash, redirect, render_template, request, send_file, url_for

import importlib
import merge_pdfs
# ensure latest edits are available in long-running test environment
merge_pdfs = importlib.reload(merge_pdfs)
merge_pdfs_bytes = getattr(merge_pdfs, "merge_pdfs_bytes", None)
merge_pdfs_fn = getattr(merge_pdfs, "merge_pdfs")


from pathlib import Path

# use package-local templates directory
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")


@app.route("/", methods=["GET"])
def index():
    try:
        return render_template("index.html")
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("files")
    if not files:
        flash("No files uploaded", "error")
        return redirect(url_for("index"))

    page_size = request.form.get("page_size") or None
    # per-file resize instructions (one per uploaded file). Values:
    # 'preserve' | 'global' | WIDTHxHEIGHT
    per_file_sizes = request.form.getlist("file_resize") or None

    with tempfile.TemporaryDirectory() as tmpdir:
        paths: List[str] = []
        for f in files:
            filename = f.filename or "upload.pdf"
            target = Path(tmpdir) / filename
            f.save(str(target))
            paths.append(str(target))

        try:
            if merge_pdfs_bytes:
                data = merge_pdfs_bytes(paths, per_file_sizes=per_file_sizes, global_size=page_size)
            else:
                # fallback to file-based merge
                out_path = Path(tmpdir) / "merged.pdf"
                merge_pdfs_fn(paths, str(out_path))
                with open(out_path, "rb") as f:
                    data = f.read()
        except Exception as exc:
            return Response(f"Error merging files: {exc}\n", status=400)

        import io

        bio = io.BytesIO(data)
        bio.seek(0)
        return send_file(bio, as_attachment=True, download_name="merged.pdf", mimetype="application/pdf")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
