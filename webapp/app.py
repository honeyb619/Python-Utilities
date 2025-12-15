from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import List

# CRITICAL: Set Werkzeug limits BEFORE importing anything else
# For Werkzeug 3.x, we need to set limits through flask.Config
os.environ['WERKZEUG_MAX_CONTENT_LENGTH'] = str(500 * 1024 * 1024)

# Load environment variables from .env file
from dotenv import load_dotenv
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

# Allow HTTP for localhost development (required for OAuth2 on http://localhost)
if os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") == "1":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Add parent directory to path so we can import merge_pdfs
sys.path.insert(0, str(project_root))

from flask import Flask, Response, flash, redirect, render_template, request, send_file, url_for, session, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

import importlib
import merge_pdfs
# ensure latest edits are available in long-running test environment
merge_pdfs = importlib.reload(merge_pdfs)
merge_pdfs_bytes = getattr(merge_pdfs, "merge_pdfs_bytes", None)
merge_pdfs_fn = getattr(merge_pdfs, "merge_pdfs")

# Create a temporary directory for session uploads
TEMP_UPLOAD_DIR = tempfile.gettempdir()
SESSION_PDFS = {}  # Store PDFs per session: {session_id: pdf_bytes}


from pathlib import Path

# use package-local templates directory
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")
# Set Flask's MAX_CONTENT_LENGTH to 500MB
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024


@app.route("/", methods=["GET"])
def index():
    try:
        return render_template("index.html")
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


@app.before_request
def log_request_info():
    """Log request info for debugging"""
    print(f"[DEBUG] {request.method} {request.path}")
    print(f"[DEBUG] Content-Length header: {request.content_length}")
    print(f"[DEBUG] MAX_CONTENT_LENGTH config: {app.config.get('MAX_CONTENT_LENGTH')}")
    

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle 413 Request Entity Too Large errors"""
    max_size_mb = app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)
    print(f"[ERROR] 413 - Content-Length: {request.content_length}, Max: {app.config.get('MAX_CONTENT_LENGTH')}")
    return Response(f"413 - Request entity too large (max {max_size_mb:.1f}MB). Content-Length: {request.content_length} bytes.\n", status=413)


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
    
    # Get custom output filename
    output_filename = request.form.get("output_filename", "").strip()
    if not output_filename:
        output_filename = "merged.pdf"
    elif not output_filename.lower().endswith(".pdf"):
        output_filename += ".pdf"

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
        return send_file(bio, as_attachment=True, download_name=output_filename, mimetype="application/pdf")


@app.route("/compress", methods=["GET"])
def compress_page():
    try:
        return render_template("compress.html")
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


@app.route("/edit", methods=["GET"])
def edit_page():
    try:
        return render_template("edit.html")
    except Exception as exc:
        return Response(f"Template error: {exc}\n", status=500)


@app.route("/edit/store-pdf", methods=["POST"])
def store_pdf():
    """Store PDF in memory/session for later signature addition"""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No PDF file uploaded"}), 400
    
    # Store PDF data in a server-side dict using session ID as key
    pdf_data = f.read()
    
    # Get or create a unique key for this user's session
    if 'pdf_upload_key' not in session:
        session['pdf_upload_key'] = str(uuid.uuid4())
        session.modified = True
    
    key = session['pdf_upload_key']
    SESSION_PDFS[key] = pdf_data
    
    return jsonify({"success": True, "size": len(pdf_data), "key": key})


@app.route("/edit/store-signature", methods=["POST"])
def store_signature():
    """Store signature image for later use"""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No signature file uploaded"}), 400
    
    signature_data = f.read()
    
    # Get or create a unique key for this user's session
    if 'signature_upload_key' not in session:
        session['signature_upload_key'] = str(uuid.uuid4())
        session.modified = True
    
    key = session['signature_upload_key']
    SESSION_PDFS[f"sig_{key}"] = signature_data  # Store with sig_ prefix to avoid conflicts
    
    return jsonify({"success": True, "size": len(signature_data), "key": key})


@app.route("/edit/add-signature", methods=["POST"])
def add_signature():
    """Add a signature image to a PDF"""
    # Get PDF from server-side storage using session key
    key = session.get('pdf_upload_key')
    if not key or key not in SESSION_PDFS:
        return Response("No PDF stored in session. Please upload PDF first.\n", status=400)
    
    pdf_data = SESSION_PDFS.get(key)
    if not pdf_data:
        return Response("PDF data not found in storage.\n", status=400)
    
    # Get signature data - either from base64 field OR from stored signature
    signature_source = request.form.get("signature_source", "draw")  # "draw", "upload", or "drawn_base64"
    
    if signature_source == "upload":
        # Retrieve stored signature from server
        sig_key = session.get('signature_upload_key')
        if not sig_key or f"sig_{sig_key}" not in SESSION_PDFS:
            return Response("No stored signature found. Please upload a signature image.\n", status=400)
        signature_data = SESSION_PDFS.get(f"sig_{sig_key}")
    else:
        # Use base64 encoded signature (for drawn signatures only)
        signature_data = request.form.get("signature_data")
        if not signature_data:
            return Response("No signature data provided.\n", status=400)
    
    page_num = int(request.form.get("page_num", 1)) - 1
    x = float(request.form.get("x", 50))
    y = float(request.form.get("y", 50))
    width = float(request.form.get("width", 100))
    height = float(request.form.get("height", 50))
    signature_date = request.form.get("signature_date", "")
    
    try:
        import io
        import tempfile
        from PIL import Image
        import base64
        from datetime import datetime
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        
        # Handle signature data based on source
        if signature_source == "upload":
            # For uploaded signatures, signature_data is already binary
            sig_image_data = signature_data
        else:
            # For drawn signatures, signature_data is base64 encoded data URI
            if signature_data.startswith("data:image"):
                signature_data = signature_data.split(",")[1]
            sig_image_data = base64.b64decode(signature_data)
        
        sig_image = Image.open(io.BytesIO(sig_image_data))
        
        # Read the PDF
        reader = PdfReader(io.BytesIO(pdf_data))
        writer = PdfWriter()
        
        # Get page dimensions
        if page_num < 0 or page_num >= len(reader.pages):
            page_num = 0
        
        page = reader.pages[page_num]
        page_height = float(page.mediabox.height)
        page_width = float(page.mediabox.width)
        
        # Resize signature to fit the specified dimensions, keeping transparency
        sig_resized = sig_image.resize((int(width), int(height)), Image.Resampling.LANCZOS)
        # Keep RGBA for transparency
        if sig_resized.mode != "RGBA":
            sig_resized = sig_resized.convert("RGBA")
        
        # Create overlay PDF with signature image using temporary file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as sig_file:
            sig_path = sig_file.name
            sig_resized.save(sig_path, format="PNG")
        
        try:
            temp_overlay = io.BytesIO()
            c = canvas.Canvas(temp_overlay, pagesize=(page_width, page_height))
            
            # Draw signature on canvas (y coordinate is from bottom in reportlab)
            c.drawImage(sig_path, x, page_height - y - height, width=width, height=height, mask='auto')
            
            # Add date below the signature in DD-MMM-YYYY format
            if signature_date:
                # Parse the provided date (YYYY-MM-DD format from date input)
                date_obj = datetime.strptime(signature_date, "%Y-%m-%d")
                date_str = date_obj.strftime("%d-%b-%Y").upper()
            else:
                # Fallback to today's date
                date_str = datetime.now().strftime("%d-%b-%Y").upper()
            date_y = page_height - y - height - 15  # 15 points below signature
            c.setFont("Helvetica", 9)
            # Center the date below the signature
            date_x = x + width / 2  # Center of signature width
            c.drawCentredString(date_x, date_y, date_str)
            
            c.save()
            
            temp_overlay.seek(0)
            
            # Read the overlay and merge with original page
            overlay_reader = PdfReader(temp_overlay)
            overlay_page = overlay_reader.pages[0]
            
            # Add all pages from original PDF, overlaying signature on specified page
            for i, orig_page in enumerate(reader.pages):
                if i == page_num:
                    orig_page.merge_page(overlay_page)
                writer.add_page(orig_page)
            
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            
            return send_file(out, as_attachment=True, download_name="signed.pdf", mimetype="application/pdf")
        finally:
            # Clean up temporary file
            import os
            try:
                os.unlink(sig_path)
            except:
                pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(f"Error adding signature: {str(e)}\n", status=400)


@app.route("/edit/add-text", methods=["POST"])
def add_text():
    """Add text to a PDF"""
    f = request.files.get("file")
    if not f:
        return Response("No PDF file uploaded\n", status=400)
    
    text = request.form.get("text", "")
    if not text:
        return Response("No text provided\n", status=400)
    
    page_num = int(request.form.get("page_num", 1)) - 1
    x = float(request.form.get("x", 50))
    y = float(request.form.get("y", 50))
    font_size = int(request.form.get("font_size", 12))
    
    try:
        import io
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        
        # Read the PDF
        pdf_data = f.read()
        reader = PdfReader(io.BytesIO(pdf_data))
        writer = PdfWriter()
        
        if page_num < 0 or page_num >= len(reader.pages):
            page_num = 0
        
        page = reader.pages[page_num]
        page_height = float(page.mediabox.height)
        page_width = float(page.mediabox.width)
        
        # Create overlay PDF with text
        temp_overlay = io.BytesIO()
        c = canvas.Canvas(temp_overlay, pagesize=(page_width, page_height))
        c.setFont("Helvetica", font_size)
        c.drawString(x, page_height - y - font_size, text)
        c.save()
        
        temp_overlay.seek(0)
        overlay_reader = PdfReader(temp_overlay)
        overlay_page = overlay_reader.pages[0]
        
        # Add all pages, overlaying text on specified page
        for i, orig_page in enumerate(reader.pages):
            if i == page_num:
                orig_page.merge_page(overlay_page)
            writer.add_page(orig_page)
        
        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        
        return send_file(out, as_attachment=True, download_name="annotated.pdf", mimetype="application/pdf")
    except Exception as e:
        return Response(f"Error adding text: {str(e)}\n", status=400)

@app.route("/compress", methods=["POST"])
def compress():
    f = request.files.get("file")
    if not f:
        return Response("No file uploaded\n", status=400)

    algo = request.form.get("algorithm", "lossless")
    remove_meta = request.form.get("remove_metadata") == "on"
    linearize = request.form.get("linearize") == "on"
    
    # Get custom output filename
    output_filename = request.form.get("output_filename", "").strip()
    if not output_filename:
        output_filename = "compressed.pdf"
    elif not output_filename.lower().endswith(".pdf"):
        output_filename += ".pdf"

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
            return send_file(out_final, as_attachment=True, download_name=output_filename, mimetype="application/pdf")

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
            return send_file(out, as_attachment=True, download_name=output_filename, mimetype="application/pdf")

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
        return send_file(out, as_attachment=True, download_name=output_filename, mimetype="application/pdf")
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


@app.route("/drive/folders", methods=["GET"])
def drive_folders():
    """List folders in Google Drive"""
    creds_dict = session.get('drive_credentials')
    if not creds_dict:
        return jsonify({"error": "Not authorized"}), 401
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(**creds_dict)
        service = build('drive', 'v3', credentials=credentials)
        
        # Query for folders in root directory
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false and 'root' in parents"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=50
        ).execute()
        
        folders = results.get('files', [])
        return jsonify({"success": True, "folders": folders})
    except Exception as e:
        return jsonify({"error": f"Failed to list folders: {str(e)}"}), 500


@app.route("/drive/create-folder", methods=["POST"])
def drive_create_folder():
    """Create a new folder in Google Drive"""
    creds_dict = session.get('drive_credentials')
    if not creds_dict:
        return jsonify({"error": "Not authorized"}), 401
    
    folder_name = request.json.get('folder_name', '').strip()
    if not folder_name:
        return jsonify({"error": "Folder name is required"}), 400
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(**creds_dict)
        service = build('drive', 'v3', credentials=credentials)
        
        # Create folder
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=file_metadata, fields='id,name').execute()
        
        return jsonify({
            "success": True,
            "folder_id": folder.get('id'),
            "folder_name": folder.get('name')
        })
    except Exception as e:
        return jsonify({"error": f"Failed to create folder: {str(e)}"}), 500


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
        folder_id = request.form.get('folder_id', '').strip()
        
        # Build file metadata
        file_metadata = {'name': filename}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
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
    app.run(debug=False, port=5000, host="127.0.0.1")
