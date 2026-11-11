#!/usr/bin/env python3
"""Render PPTX using LibreOffice, then export page PNGs and a contact sheet."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path


def render(input_path, output_dir, width=1600, columns=3):
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("Install PyMuPDF first: python -m pip install pymupdf") from error
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
    if width < 320 or width > 6000 or columns < 1 or columns > 8:
        raise ValueError("Use a width between 320 and 6000 pixels and 1 to 8 columns")
    if not input_path.is_file():
        raise ValueError(f"Input file does not exist: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / (input_path.stem + ".pdf")
    if input_path.suffix.lower() == ".pdf":
        if input_path != pdf_path:
            shutil.copyfile(input_path, pdf_path)
    else:
        executable = shutil.which("soffice") or shutil.which("libreoffice")
        if not executable:
            for candidate in ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "C:/Program Files/LibreOffice/program/soffice.exe"):
                if Path(candidate).is_file():
                    executable = candidate
                    break
        if not executable:
            raise RuntimeError("Install LibreOffice and put soffice or libreoffice on PATH, then rerun this command")
        with tempfile.TemporaryDirectory(prefix="paperclay-render-") as temp:
            temp_path = Path(temp)
            profile = (temp_path / "profile").as_uri()
            result = subprocess.run([executable, "-env:UserInstallation=" + profile, "--headless", "--convert-to", "pdf:impress_pdf_Export", "--outdir", str(temp_path), str(input_path)], capture_output=True, text=True, timeout=180, check=False)
            exported = temp_path / (input_path.stem + ".pdf")
            if result.returncode or not exported.exists():
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeError("LibreOffice could not export this deck: " + detail)
            shutil.copyfile(exported, pdf_path)
    paths = []
    with fitz.open(pdf_path) as document:
        if not len(document):
            raise RuntimeError("The rendered PDF has no pages")
        for number, page in enumerate(document, 1):
            target = output_dir / f"slide-{number:02d}.png"
            page.get_pixmap(matrix=fitz.Matrix(width / page.rect.width, width / page.rect.width), alpha=False).save(target)
            paths.append(target)
    contact = None
    warning = None
    try:
        from PIL import Image, ImageDraw
        thumb_width, gap, label_height = min(width, 520), 20, 26
        with Image.open(paths[0]) as image:
            thumb_height = round(thumb_width * image.height / image.width)
        rows = math.ceil(len(paths) / columns)
        contact = output_dir / "contact_sheet.png"
        sheet = Image.new("RGB", (gap + columns * (thumb_width + gap), gap + rows * (thumb_height + label_height + gap)), "#E7E6E2")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(paths):
            x = gap + index % columns * (thumb_width + gap)
            y = gap + index // columns * (thumb_height + label_height + gap)
            draw.text((x, y + 3), f"{index + 1:02d}", fill="#343430")
            with Image.open(path) as image:
                image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
                sheet.paste(image, (x, y + label_height))
        sheet.save(contact)
    except ImportError:
        warning = "Page PNGs are ready. Install Pillow to add a contact sheet: python -m pip install pillow"
    return {"pdf": str(pdf_path), "pages": [str(path) for path in paths], "contact_sheet": str(contact) if contact else None, "warning": warning}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()
    try:
        result = render(args.input, args.output_dir, args.width, args.columns)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(2, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
