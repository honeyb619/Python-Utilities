from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List

from flask import Flask, Response, flash, redirect, render_template, request, send_file, url_for, session, jsonify

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


@app.route("/compress", methods=["GET"])
def compress_page():
    try:
        return render_template("compress.html")
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


@app.route("/compress", methods=["POST"])
def compress():
    f = request.files.get("file")
    if not f:
        return Response("No file uploaded\n", status=400)

    algo = request.form.get("algorithm", "lossless")
    remove_meta = request.form.get("remove_metadata") == "on"
    linearize = request.form.get("linearize") == "on"

    import io
    from PyPDF2 import PdfReader, PdfWriter

    try:
        data = f.read()
        # If using optimize, try pikepdf path first
        if algo == "optimize":
            try:
                import pikepdf  # type: ignore
            except Exception:
                return Response(
                    "Optimize requires 'pikepdf' to be installed. Try: pip install pikepdf\n",
                    status=400,
                )

            src_io = io.BytesIO(data)
            pdf = pikepdf.Pdf.open(src_io)

            # optionally remove metadata (DocInfo and XMP)
            if remove_meta:
                try:
                    pdf.docinfo.clear()
                except Exception:
                    pass
                try:
                    if hasattr(pdf, "Root") and "Metadata" in pdf.Root:
                        del pdf.Root["Metadata"]
                except Exception:
                    pass

            input_size = len(data)

            # First attempt: conservative optimization
            out1 = io.BytesIO()
            kwargs1: dict = {"compress_streams": True, "object_streams": True}
            try:
                if hasattr(pikepdf, "StreamDecodeLevel"):
                    kwargs1["stream_decode_level"] = pikepdf.StreamDecodeLevel.special  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                kwargs1["recompress_flate"] = True
            except Exception:
                pass
            if linearize:
                kwargs1["linearize"] = True

            try:
                pdf.save(out1, **kwargs1)
            except TypeError:
                # fallback: minimal safe options
                pdf.save(out1, compress_streams=True, object_streams=True)

            size1 = out1.getbuffer().nbytes

            # Second attempt: aggressive optimization if not improved
            use_second = size1 >= input_size
            out_final = out1

            if use_second and hasattr(pikepdf, "StreamDecodeLevel"):
                out2 = io.BytesIO()
                kwargs2: dict = {"compress_streams": True, "object_streams": True}
                try:
                    kwargs2["stream_decode_level"] = pikepdf.StreamDecodeLevel.all  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    kwargs2["recompress_flate"] = True
                except Exception:
                    pass
                if linearize:
                    kwargs2["linearize"] = True
                try:
                    pdf.save(out2, **kwargs2)
                    if out2.getbuffer().nbytes < size1:
                        out_final = out2
                except Exception:
                    # keep first attempt if second fails
                    pass

            out_final.seek(0)
            return send_file(out_final, as_attachment=True, download_name="compressed.pdf", mimetype="application/pdf")

        # Handle image downscale algorithm
        if algo == "downscale":
            try:
                import pikepdf  # type: ignore
            except Exception:
                return Response(
                    "Downscale requires 'pikepdf' to be installed. Try: pip install pikepdf\n",
                    status=400,
                )
            try:
                from PIL import Image  # type: ignore
            except Exception:
                return Response(
                    "Downscale requires 'Pillow' to be installed. Try: pip install pillow\n",
                    status=400,
                )

            max_px = int(request.form.get("max_px", 2000))
            jpeg_quality = int(request.form.get("jpeg_quality", 75))

            pdf = pikepdf.Pdf.open(io.BytesIO(data))
            changed = False
            for page in pdf.pages:
                try:
                    resources = page.get("/Resources", pikepdf.Dictionary())
                    xobj = resources.get("/XObject", pikepdf.Dictionary())
                except Exception:
                    continue
                for name, obj in list(xobj.items()):
                    try:
                        if not isinstance(obj, pikepdf.Object):
                            continue
                        obj_dict = obj.get_object()
                        if obj_dict.get("/Subtype") != pikepdf.Name("/Image"):
                            continue
                        # Extract image via PdfImage helper
                        try:
                            img = pikepdf.PdfImage(obj_dict)
                            pil = img.as_pil_image()
                        except Exception:
                            continue
                        # Only downscale if larger than threshold
                        if pil.width <= max_px and pil.height <= max_px:
                            continue
                        # Resize in place with aspect ratio
                        from PIL import Image as PILImage
                        pil.thumbnail((max_px, max_px), PILImage.LANCZOS)
                        # Ensure RGB for JPEG
                        if pil.mode not in ("RGB",):
                            pil = pil.convert("RGB")
                        buf = io.BytesIO()
                        pil.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
                        buf.seek(0)
                        # Replace stream and key metadata
                        try:
                            obj_dict["/Filter"] = pikepdf.Name("/DCTDecode")
                            obj_dict["/ColorSpace"] = pikepdf.Name("/DeviceRGB")
                            obj_dict["/BitsPerComponent"] = 8
                            obj_dict["/Width"] = pil.width
                            obj_dict["/Height"] = pil.height
                            # remove potential incompatible keys
                            for k in ("/SMask", "/Mask", "/DecodeParms", "/Decode"):
                                if k in obj_dict:
                                    del obj_dict[k]
                            obj_dict.stream = buf.getvalue()
                            changed = True
                        except Exception:
                            continue
                    except Exception:
                        continue
            out = io.BytesIO()
            try:
                pdf.save(out, compress_streams=True, object_streams=True)
            except Exception:
                pdf.save(out)
            out.seek(0)
            return send_file(out, as_attachment=True, download_name="compressed.pdf", mimetype="application/pdf")

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return Response("Cannot read encrypted PDF without password\n", status=400)

        writer = PdfWriter()

        for page in reader.pages:
            try:
                # best-effort lossless content stream compression (if available)
                if hasattr(page, "compress_content_streams") and algo == "lossless":
                    page.compress_content_streams()  # type: ignore[attr-defined]
            except Exception:
                # continue even if a page fails to compress
                pass
            writer.add_page(page)

        if remove_meta:
            # overwrite metadata with empty dict
            try:
                writer.add_metadata({})
            except Exception:
                pass
        else:
            try:
                if reader.metadata:
                    writer.add_metadata(reader.metadata)  # type: ignore[arg-type]
            except Exception:
                pass

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, as_attachment=True, download_name="compressed.pdf", mimetype="application/pdf")
    except Exception as exc:
        return Response(f"Error compressing file: {exc}\n", status=400)


# Google Drive integration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/drive/callback")]
    }
}


@app.route("/drive/auth")
def drive_auth():
    """Redirect user to Google OAuth consent screen"""
    if not CLIENT_CONFIG["web"]["client_id"]:
        return Response("Google Drive not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.\n", status=400)
    
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
        flow.redirect_uri = CLIENT_CONFIG["web"]["redirect_uris"][0]
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        session['state'] = state
        return redirect(authorization_url)
    except Exception as e:
        return Response(f"Error initializing Google Drive auth: {e}\n", status=500)


@app.route("/drive/callback")
def drive_callback():
    """Handle OAuth callback from Google"""
    try:
        from google_auth_oauthlib.flow import Flow
        state = session.get('state')
        
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=state)
        flow.redirect_uri = CLIENT_CONFIG["web"]["redirect_uris"][0]
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Store credentials in session (in production, use database)
        session['drive_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        flash("Successfully connected to Google Drive!", "success")
        return redirect(url_for('drive_settings'))
    except Exception as e:
        return Response(f"Error completing Google Drive auth: {e}\n", status=500)


@app.route("/drive/upload", methods=["POST"])
def drive_upload():
    """Upload a file to Google Drive"""
    creds_dict = session.get('drive_credentials')
    if not creds_dict:
        return jsonify({"error": "Not authorized. Please connect to Google Drive first."}), 401
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        
        credentials = Credentials(**creds_dict)
        service = build('drive', 'v3', credentials=credentials)
        
        # Get file from request
        file_data = request.files.get('file')
        if not file_data:
            return jsonify({"error": "No file provided"}), 400
        
        filename = request.form.get('filename', file_data.filename or 'document.pdf')
        
        file_metadata = {'name': filename}
        media = MediaInMemoryUpload(file_data.read(), mimetype='application/pdf', resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        return jsonify({
            "success": True,
            "file_id": file.get('id'),
            "name": file.get('name'),
            "link": file.get('webViewLink')
        })
    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/drive/disconnect", methods=["POST"])
def drive_disconnect():
    """Disconnect Google Drive"""
    session.pop('drive_credentials', None)
    session.pop('state', None)
    flash("Disconnected from Google Drive", "info")
    return redirect(url_for('drive_settings'))


@app.route("/drive/settings")
def drive_settings():
    """Drive settings page"""
    connected = 'drive_credentials' in session
    try:
        return render_template("drive_settings.html", connected=connected)
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
