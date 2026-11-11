#!/usr/bin/env python3
"""Inspect actual PowerPoint placeholders and compare them with the layout catalog."""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from ooxml import EMU, NS, inherit_geometry, ordered_slides, read_package, shape_bounds, shape_key, shape_name, shape_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def inspect(path, layout_id=None):
    path = Path(path)
    parts = read_package(path)
    catalog_path = path.with_name("layouts.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {"layouts": []}
    by_slide = {int(item["slide"]): item for item in catalog["layouts"]}
    found = []
    for index, part in enumerate(ordered_slides(parts), 1):
        item = by_slide.get(index, {"id": f"slide-{index}", "name": f"Slide {index}"})
        if layout_id and item["id"] != layout_id:
            continue
        root = ET.fromstring(parts[part])
        inherit_geometry(parts, root, part)
        placeholders = []
        for shape in root.findall("p:cSld/p:spTree/*", NS):
            ph = shape.find(".//p:ph", NS)
            key = shape_key(shape)
            if ph is None and not key:
                continue
            bounds = shape_bounds(shape)
            placeholders.append({"key": key, "name": shape_name(shape), "native_type": ph.get("type", "obj") if ph is not None else None, "index": ph.get("idx", "0") if ph is not None else None, "text": shape_text(shape), "bounds_px": dict(zip(("x", "y", "w", "h"), [round(v / EMU, 2) for v in bounds])) if bounds else None, "guide": item.get("fields", {}).get(key)})
        found.append({"slide": index, "id": item["id"], "name": item["name"], "description": item.get("description", ""), "placeholders": placeholders})
    if layout_id and not found:
        raise ValueError("No layout with id: " + layout_id)
    root = ET.fromstring(parts["ppt/presentation.xml"])
    size = root.find("p:sldSz", NS)
    return {"template": str(path.resolve()), "slide_count": len(ordered_slides(parts)), "canvas_px": {"width": int(size.get("cx")) / EMU, "height": int(size.get("cy")) / EMU}, "layouts": found}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ASSETS / "paperclay.pptx")
    parser.add_argument("--layout", help="Exact catalog layout id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = json.dumps(inspect(args.input, args.layout), ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result + "\n", encoding="utf-8")
        else:
            print(result)
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
