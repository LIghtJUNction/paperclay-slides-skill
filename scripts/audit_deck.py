#!/usr/bin/env python3
"""Check package links, placeholder residue, bounds, and chart caches before rendering."""
from __future__ import annotations

import argparse
import json
import math
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from ooxml import EMU, NS, inherit_geometry, ordered_slides, read_package, resolve_target, shape_bounds, shape_key, shape_name, shape_text, tag


def audit(path, allow_placeholders=False):
    parts = read_package(Path(path))
    errors, warnings = [], []
    for name, data in parts.items():
        if not name.endswith(".rels"):
            continue
        root = ET.fromstring(data)
        if name == "_rels/.rels":
            owner = ""
        else:
            directory, filename = name.rsplit("/_rels/", 1)
            owner = posixpath.join(directory, filename[:-5])
        ids = set()
        for rel in root:
            rid = rel.get("Id")
            if rid in ids:
                errors.append(f"Duplicate relationship {rid} in {name}")
            ids.add(rid)
            if rel.get("TargetMode") == "External":
                continue
            target = resolve_target(owner, rel.get("Target", ""))
            if target not in parts:
                errors.append(f"Missing relationship target: {name} -> {target}")
    presentation = ET.fromstring(parts["ppt/presentation.xml"])
    size = presentation.find("p:sldSz", NS)
    slide_w, slide_h = int(size.get("cx")), int(size.get("cy"))
    slides = ordered_slides(parts)
    counts = {"text_shapes": 0, "pictures": 0, "tables": 0, "charts": 0, "native_placeholders": 0}
    for number, part in enumerate(slides, 1):
        root = ET.fromstring(parts[part])
        inherit_geometry(parts, root, part)
        counts["pictures"] += len(root.findall(".//p:pic", NS))
        counts["tables"] += len(root.findall(".//a:tbl", NS))
        counts["charts"] += len(root.findall(".//c:chart", NS))
        counts["native_placeholders"] += len(root.findall(".//p:ph", NS))
        for shape in root.findall("p:cSld/p:spTree/*", NS):
            name = shape_name(shape)
            bounds = shape_bounds(shape)
            if bounds:
                x, y, width, height = bounds
                tolerance = 2 * EMU
                if width < 0 or height < 0 or x < -tolerance or y < -tolerance or x + width > slide_w + tolerance or y + height > slide_h + tolerance:
                    errors.append(f"Slide {number}: '{name}' extends outside the canvas")
            text = shape_text(shape)
            if not text.strip():
                continue
            counts["text_shapes"] += 1
            if shape_key(shape) and (re.fullmatch(r"\s*\[[^\]]{1,160}\]\s*", text) or "{{" in text):
                if not allow_placeholders:
                    errors.append(f"Slide {number}: unfilled placeholder '{name}': {text}")
                continue
            # This is a conservative text-capacity warning, not font-engine measurement.
            sizes = [int(node.get("sz")) * 127 for node in shape.findall(".//a:rPr", NS) + shape.findall(".//a:defRPr", NS) if node.get("sz")]
            if not sizes or not bounds:
                continue
            font = max(sizes)
            x, y, width, height = bounds
            body = shape.find("p:txBody/a:bodyPr", NS)
            if body is not None:
                width -= int(body.get("lIns", 91440)) + int(body.get("rIns", 91440))
                height -= int(body.get("tIns", 45720)) + int(body.get("bIns", 45720))
            lines = 0
            for line in text.split("\n"):
                approximate_width = sum(1 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.54 for ch in line) * font
                lines += max(1, math.ceil(approximate_width / max(1, width)))
            if lines * font * 1.05 > height * 1.12:
                warnings.append(f"Slide {number}: '{name}' may be too long ({lines} estimated lines); inspect the rendered page")
    for name, data in parts.items():
        if name.startswith("ppt/charts/") and name.endswith(".xml") and "/_rels/" not in name:
            root = ET.fromstring(data)
            for cache in root.findall(".//c:numCache", NS) + root.findall(".//c:strCache", NS):
                count = cache.find("c:ptCount", NS)
                points = cache.findall("c:pt", NS)
                if count is None or int(count.get("val", -1)) != len(points):
                    errors.append(f"Chart cache length mismatch: {name}")
            for series in root.findall(".//c:ser", NS):
                categories = series.findall("c:cat/c:strRef/c:strCache/c:pt", NS)
                values = series.findall("c:val/c:numRef/c:numCache/c:pt", NS)
                if categories and len(categories) != len(values):
                    errors.append(f"Chart category/value length mismatch: {name}")
    return {"input": str(Path(path).resolve()), "slides": len(slides), "objects": counts, "errors": errors, "warnings": warnings, "ok": not errors, "scope": "Structural checks and estimated text capacity. Render every slide to assess typography and clipping."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--allow-placeholders", action="store_true", help="Use when auditing the reusable template itself")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.input, args.allow_placeholders)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
        print(output)
        raise SystemExit(0 if result["ok"] else 1)
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
