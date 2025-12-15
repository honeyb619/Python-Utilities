#!/usr/bin/env python3
"""Merge PDF files.

Usage examples:
  python merge_pdfs.py file1.pdf file2.pdf -o merged.pdf
  python merge_pdfs.py -o combined.pdf  # merges all PDFs in current dir
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

from PyPDF2 import PdfReader, PdfWriter

import io


def merge_pdfs(files: Iterable[str], output: str) -> str:
    """Merge the list of PDF filenames into `output`.

    Raises ValueError if any input file cannot be read (e.g., encrypted).
    Returns the output filename on success.
    """
    writer = PdfWriter()
    files_list: List[str] = list(files)
    for f in files_list:
        path = Path(f)
        if not path.exists() or not path.is_file():
            raise ValueError(f"File not found: {f}")
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            try:
                # try decrypt with empty password
                reader.decrypt("")
            except Exception:
                raise ValueError(f"Encrypted PDF: {f}")
        for p in reader.pages:
            writer.add_page(p)

    with open(output, "wb") as out_f:
        writer.write(out_f)
    return output


def _gather_files(args: argparse.Namespace) -> List[str]:
    files: List[str] = []
    if args.files:
        for item in args.files:
            p = Path(item)
            if p.is_dir():
                pattern = "**/*.pdf" if args.recursive else "*.pdf"
                files.extend(sorted(str(x) for x in p.glob(pattern) if x.is_file()))
            else:
                files.append(str(p))
    else:
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        files = sorted(str(x) for x in Path('.').glob(pattern) if x.is_file())
    return files


def _parse_size(size: str) -> tuple[float, float]:
    """Parse size strings like '612x792', '8.5inx11in', '210mmx297mm'. Returns (width, height) in points."""
    def to_pts(val: str) -> float:
        val = val.strip()
        if val.endswith("mm"):
            return float(val[:-2]) * 72.0 / 25.4
        if val.endswith("in"):
            return float(val[:-2]) * 72.0
        if val.endswith("pt"):
            return float(val[:-2])
        return float(val)  # assume points

    if "x" not in size:
        raise ValueError("Size must be in WIDTHxHEIGHT format")
    w_s, h_s = size.split("x", 1)
    return to_pts(w_s), to_pts(h_s)


def _choose_target_size(pages, size_arg: str | None) -> tuple[float, float]:
    widths = [float(p.mediabox.width) for p in pages]
    heights = [float(p.mediabox.height) for p in pages]
    if not size_arg or size_arg.lower() == "largest":
        return max(widths), max(heights)
    if size_arg.lower() == "smallest":
        return min(widths), min(heights)
    if size_arg.lower() == "first":
        return widths[0], heights[0]
    # custom sizes
    return _parse_size(size_arg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Merge PDF files")
    p.add_argument("files", nargs="*", help="PDF files or directories to merge")
    p.add_argument("-o", "--output", default="merged.pdf", help="Output filename")
    p.add_argument("-r", "--recursive", action="store_true", help="Search directories recursively")
    p.add_argument(
        "--page-size",
        default="largest",
        help=(
            "Target page size. Use 'largest', 'smallest', 'first' or WIDTHxHEIGHT with units "
            "(e.g. 8.5inx11in, 210mmx297mm, 612x792). Units: pt, mm, in. Default 'largest'."
        ),
    )
    args = p.parse_args(argv)

    files = _gather_files(args)
    if not files:
        print("No PDF files found.", file=sys.stderr)
        return 2

    # read pages first to be able to choose a target size
    try:
        pages = []
        for f in files:
            try:
                reader = PdfReader(str(f))
            except Exception as e:
                raise ValueError(f"There was a problem reading the document: {f}: {e}")
            pages.extend(reader.pages)

        size_arg = args.page_size
        target_w, target_h = _choose_target_size(pages, size_arg)
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        return 1

    # perform the merge and resizing
    try:
        writer = PdfWriter()
        for f in files:
            reader = PdfReader(str(f))
            for p in reader.pages:
                w = float(p.mediabox.width)
                h = float(p.mediabox.height)
                scale_x = target_w / w if w else 1.0
                scale_y = target_h / h if h else 1.0
                scale = min(scale_x, scale_y)
                # preserve aspect ratio when possible
                try:
                    if hasattr(p, "scale_to"):
                        p.scale_to(w * scale, h * scale)
                    elif hasattr(p, "scale_by"):
                        p.scale_by(scale)
                    elif hasattr(p, "scale"):
                        p.scale(scale)
                    else:
                        # fallback: leave content and change mediabox (may crop or stretch)
                        pass
                except Exception:
                    pass

                # ensure the page MediaBox is the target size (keeps consistent output size)
                llx = float(p.mediabox.lower_left[0])
                lly = float(p.mediabox.lower_left[1])
                p.mediabox.upper_right = (llx + target_w, lly + target_h)
                writer.add_page(p)

        with open(args.output, "wb") as out_f:
            writer.write(out_f)

        print(f"Merged {len(files)} file(s) into {args.output} with pages {int(target_w)}x{int(target_h)} pts")
        return 0
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        return 1


def merge_pdfs_bytes(files: Iterable[str], per_file_sizes: list[str] | None = None, global_size: str | None = None) -> bytes:
    """Merge files and return PDF bytes.

    per_file_sizes: optional list with same length as `files`. Each entry may be:
      - 'preserve' (no resizing)
      - 'global' (use global_size)
      - WIDTHxHEIGHT string (e.g. '8.5inx11in') to resize this file's pages
    global_size: optional size string used when an entry is 'global'
    """
    files_list: List[str] = list(files)
    # read pages to compute global target size if needed
    all_pages = []
    for f in files_list:
        reader = PdfReader(str(f))
        all_pages.extend(reader.pages)

    global_target: tuple[float, float] | None = None
    if global_size and global_size.lower() != "preserve":
        global_target = _choose_target_size(all_pages, global_size)

    writer = PdfWriter()
    for idx, f in enumerate(files_list):
        reader = PdfReader(str(f))
        # determine target for this file
        target = None
        if per_file_sizes and idx < len(per_file_sizes):
            spec = per_file_sizes[idx]
            if not spec or spec == "preserve":
                target = None
            elif spec == "global":
                target = global_target
            elif isinstance(spec, str) and spec.lower() == "a4":
                target = _parse_size("210mmx297mm")
            elif isinstance(spec, str) and spec.lower() in ("letter", "let"):
                target = _parse_size("8.5inx11in")
            else:
                target = _parse_size(spec)
        else:
            # fall back to global target if provided
            target = global_target

        for p in reader.pages:
            if target:
                target_w, target_h = target
                w = float(p.mediabox.width)
                h = float(p.mediabox.height)
                scale_x = target_w / w if w else 1.0
                scale_y = target_h / h if h else 1.0
                scale = min(scale_x, scale_y)
                try:
                    if hasattr(p, "scale_to"):
                        p.scale_to(w * scale, h * scale)
                    elif hasattr(p, "scale_by"):
                        p.scale_by(scale)
                    elif hasattr(p, "scale"):
                        p.scale(scale)
                except Exception:
                    pass
                llx = float(p.mediabox.lower_left[0])
                lly = float(p.mediabox.lower_left[1])
                p.mediabox.upper_right = (llx + target_w, lly + target_h)

            writer.add_page(p)

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    raise SystemExit(main())
