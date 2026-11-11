#!/usr/bin/env python3
"""Fill and repeat Paperclay layouts from JSON without changing their typography."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from ooxml import (
    NS, REL, add_default, add_override, add_rel, el, image_size, inherit_geometry,
    make_chart, make_picture, make_table, ordered_slides, read_package,
    relationships, rels_path, resolve_target, set_text, shape_key,
    tag, write_package, xml_bytes,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def add_notes(parts, types, slide_number, text, slide_rels):
    """Write independent notes so repeated layouts never share the same notes page."""
    notes = el("p:notes")
    tree = el("p:spTree", parent=el("p:cSld", parent=notes))
    nv = el("p:nvGrpSpPr", parent=tree)
    el("p:cNvPr", {"id": 1, "name": ""}, nv)
    el("p:cNvGrpSpPr", parent=nv)
    el("p:nvPr", parent=nv)
    el("p:grpSpPr", parent=tree)
    shape = el("p:sp", parent=tree)
    nv = el("p:nvSpPr", parent=shape)
    el("p:cNvPr", {"id": 2, "name": "Notes"}, nv)
    el("p:cNvSpPr", parent=nv)
    el("p:ph", {"type": "body", "idx": 1}, el("p:nvPr", parent=nv))
    el("p:spPr", parent=shape)
    body = el("p:txBody", parent=shape)
    el("a:bodyPr", parent=body)
    el("a:lstStyle", parent=body)
    for line in text.split("\n"):
        el("a:t", parent=el("a:r", parent=el("a:p", parent=body)), text=line)
    el("a:masterClrMapping", parent=el("p:clrMapOvr", parent=notes))
    part = f"ppt/notesSlides/notesSlide{slide_number}.xml"
    nr = el("pr:Relationships")
    add_rel(nr, "slide", f"../slides/slide{slide_number}.xml")
    master_part = "ppt/notesMasters/notesMaster1.xml"
    if master_part not in parts:
        master = el("p:notesMaster")
        master.append(copy.deepcopy(notes.find("p:cSld", NS)))
        # The master defines geometry, not the slide's actual notes.
        set_text(master.find("p:cSld/p:spTree/p:sp", NS), "")
        el("p:clrMap", {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2", **{f"accent{i}": f"accent{i}" for i in range(1, 7)}, "hlink": "hlink", "folHlink": "folHlink"}, master)
        el("p:notesStyle", parent=master)
        parts[master_part] = xml_bytes(master)
        mr = el("pr:Relationships")
        themes = sorted(name for name in parts if name.startswith("ppt/theme/") and name.endswith(".xml"))
        if themes:
            add_rel(mr, "theme", "../theme/" + Path(themes[0]).name)
        parts[rels_path(master_part)] = xml_bytes(mr)
        add_override(types, master_part, "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml")
    add_rel(nr, "notesMaster", "../notesMasters/notesMaster1.xml")
    add_rel(slide_rels, "notesSlide", f"../notesSlides/notesSlide{slide_number}.xml")
    parts[part] = xml_bytes(notes)
    parts[rels_path(part)] = xml_bytes(nr)
    add_override(types, part, "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml")


def validate_entry(entry, layout, allow_overflow):
    if not isinstance(entry, dict):
        raise ValueError("Each slides item must be a JSON object")
    fields = layout["fields"]
    values = {}
    accepted = {"text": {"text", "title", "subtitle", "body", "content"}, "images": {"picture", "image"}, "tables": {"table", "tbl"}, "charts": {"chart"}}
    for category, types in accepted.items():
        group = entry.get(category, {})
        if not isinstance(group, dict):
            raise ValueError(f"{category} must be an object mapping placeholder keys to content")
        for key, value in group.items():
            if key not in fields:
                raise ValueError(f"Unknown field '{key}' in layout '{layout['id']}'")
            if key in values:
                raise ValueError(f"Field '{key}' was supplied in more than one content group")
            field_type = fields[key].get("type", "text")
            if field_type not in types:
                raise ValueError(f"Field '{key}' is {field_type}; it cannot be filled through {category}")
            if category == "text":
                if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                    raise ValueError(f"Text field '{key}' must contain text or a number")
                value = str(value)
                maximum = fields[key].get("max_chars")
                if maximum and len(value) > maximum:
                    message = f"'{key}' has {len(value)} characters, above this layout's {maximum}-character guide; shorten it or select a wider layout"
                    if not allow_overflow:
                        raise ValueError(message)
                    print("Warning: " + message, file=sys.stderr)
            values[key] = (category, value)
    for key, field in fields.items():
        if field.get("required") and key not in ("page", "brand"):
            if key not in values or values[key][1] is None or not str(values[key][1]).strip():
                raise ValueError(f"Required field '{key}' is missing in layout '{layout['id']}'")
    return values


def compose(spec_path, output, template=ASSETS / "paperclay.pptx", catalog_path=None, allow_overflow=False):
    spec_path, output, template = Path(spec_path).resolve(), Path(output).resolve(), Path(template).resolve()
    if output == template:
        raise ValueError("Write to a new file; the reusable template must remain unchanged")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not isinstance(spec.get("slides"), list) or not spec["slides"]:
        raise ValueError("The specification needs a non-empty slides array")
    catalog_path = Path(catalog_path) if catalog_path else template.with_name("layouts.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    layouts = {item["id"]: item for item in catalog["layouts"]}
    source = read_package(template)
    source_slides = ordered_slides(source)
    # Layouts, masters, themes, and any licensed template media stay intact.
    parts = {name: value for name, value in source.items() if not name.startswith(("ppt/slides/", "ppt/notesSlides/"))}
    types = ET.fromstring(parts["[Content_Types].xml"])
    for item in list(types):
        if item.get("PartName", "").startswith(("/ppt/slides/", "/ppt/notesSlides/")):
            types.remove(item)
    root = ET.fromstring(parts["ppt/presentation.xml"])
    ids = root.find("p:sldIdLst", NS)
    if ids is None:
        ids = el("p:sldIdLst")
        root.insert(1 if root.find("p:sldMasterIdLst", NS) is not None else 0, ids)
    ids.clear()
    pr = relationships(parts, "ppt/presentation.xml")
    for relation in list(pr):
        if relation.get("Type") == REL + "slide":
            pr.remove(relation)
    # Remove source sections/custom shows that refer to old slide identifiers.
    for child in list(root):
        if child.tag in (tag("p:custShowLst"), tag("p:extLst")):
            root.remove(child)
    media_number = chart_number = 0
    notes_used = False
    report = []
    for number, entry in enumerate(spec["slides"], 1):
        if not isinstance(entry, dict) or entry.get("layout") not in layouts:
            raise ValueError(f"Slide {number}: unknown layout '{entry.get('layout') if isinstance(entry, dict) else entry}'. Available: {', '.join(layouts)}")
        layout = layouts[entry["layout"]]
        values = validate_entry(entry, layout, allow_overflow)
        if "brand" in layout["fields"] and "brand" not in values:
            values["brand"] = ("text", str(spec.get("footer", "")))
        if "page" in layout["fields"] and "page" not in values:
            values["page"] = ("text", str(number))
        source_number = int(layout["slide"])
        if source_number < 1 or source_number > len(source_slides):
            raise ValueError(f"Catalog layout '{layout['id']}' refers to missing slide {source_number}")
        original_part = source_slides[source_number - 1]
        slide = ET.fromstring(source[original_part])
        inherit_geometry(source, slide, original_part)
        sr = relationships(source, original_part)
        for relation in list(sr):
            if relation.get("Type") == REL + "notesSlide":
                sr.remove(relation)
        part = f"ppt/slides/slide{number}.xml"
        tree = slide.find("p:cSld/p:spTree", NS)
        if tree is None:
            raise ValueError(f"Template slide {source_number} has no shape tree")
        found = set()
        for index, shape in list(enumerate(list(tree))):
            key = shape_key(shape)
            if not key:
                continue
            found.add(key)
            category, value = values.get(key, ("text", ""))
            if key not in values and layout["fields"].get(key, {}).get("type") in ("picture", "image", "table", "tbl", "chart"):
                tree.remove(shape)
                continue
            if category == "text":
                set_text(shape, value)
                continue
            if not isinstance(value, dict):
                raise ValueError(f"Slide {number}, field '{key}': {category} content must be an object")
            if category == "images":
                raw_path = value.get("path")
                if not isinstance(raw_path, str) or not raw_path:
                    raise ValueError(f"Image field '{key}' needs a path")
                path = (spec_path.parent / raw_path).resolve()
                data = path.read_bytes()
                width, height, extension, mime = image_size(data)
                media_number += 1
                image_part = f"ppt/media/paperclay-image-{media_number}.{extension}"
                while image_part in parts:
                    media_number += 1
                    image_part = f"ppt/media/paperclay-image-{media_number}.{extension}"
                parts[image_part] = data
                add_default(types, extension, mime)
                rid = add_rel(sr, "image", "../media/" + Path(image_part).name)
                replacement = make_picture(shape, rid, width, height, value.get("fit", "cover"))
            elif category == "tables":
                replacement = make_table(shape, value.get("headers"), value.get("rows"))
            else:
                chart_number += 1
                chart_part = f"ppt/charts/paperclay-chart-{chart_number}.xml"
                while chart_part in parts:
                    chart_number += 1
                    chart_part = f"ppt/charts/paperclay-chart-{chart_number}.xml"
                workbook_part = f"ppt/embeddings/paperclay-chart-{chart_number}.xlsx"
                rid = add_rel(sr, "chart", "../charts/" + Path(chart_part).name)
                replacement, chart_data, workbook_data = make_chart(shape, value, rid)
                parts[chart_part], parts[workbook_part] = chart_data, workbook_data
                cr = el("pr:Relationships")
                add_rel(cr, "package", "../embeddings/" + Path(workbook_part).name)
                parts[rels_path(chart_part)] = xml_bytes(cr)
                add_override(types, chart_part, "application/vnd.openxmlformats-officedocument.drawingml.chart+xml")
                add_default(types, "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            # Use the current sibling position because earlier optional slots may be removed.
            position = list(tree).index(shape)
            tree.remove(shape)
            tree.insert(position, replacement)
        missing = set(values) - found
        if missing:
            raise ValueError(f"Template does not contain named placeholders: {', '.join(sorted(missing))}")
        if entry.get("notes"):
            if not isinstance(entry["notes"], str):
                raise ValueError("Slide notes must be text")
            add_notes(parts, types, number, entry["notes"], sr)
            notes_used = True
        parts[part] = xml_bytes(slide)
        parts[rels_path(part)] = xml_bytes(sr)
        add_override(types, part, "application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
        rid = add_rel(pr, "slide", f"slides/slide{number}.xml")
        el("p:sldId", {"id": 255 + number, tag("r:id"): rid}, ids)
        report.append({"slide": number, "layout": layout["id"], "fields_filled": sorted(values)})
    if notes_used and root.find("p:notesMasterIdLst", NS) is None:
        notes_master_id = next((item.get("Id") for item in pr if item.get("Type") == REL + "notesMaster"), None)
        if not notes_master_id:
            notes_master_id = add_rel(pr, "notesMaster", "notesMasters/notesMaster1.xml")
        note_ids = el("p:notesMasterIdLst")
        el("p:notesMasterId", {tag("r:id"): notes_master_id}, note_ids)
        root.insert(list(root).index(ids), note_ids)
    # A .potx input produces an ordinary .pptx output.
    add_override(types, "ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml")
    parts["[Content_Types].xml"] = xml_bytes(types)
    parts["ppt/presentation.xml"] = xml_bytes(root)
    parts[rels_path("ppt/presentation.xml")] = xml_bytes(pr)
    # A layout's guide text must never reappear after an optional slot is omitted.
    for name in list(parts):
        if name.startswith("ppt/slideLayouts/") and name.endswith(".xml") and "/_rels/" not in name:
            layout_root = ET.fromstring(parts[name])
            for shape in layout_root.findall("p:cSld/p:spTree/p:sp", NS):
                if shape.find(".//p:ph", NS) is not None and shape.find("p:txBody", NS) is not None:
                    set_text(shape, "")
            parts[name] = xml_bytes(layout_root)
    if "docProps/core.xml" in parts:
        core = ET.fromstring(parts["docProps/core.xml"])
        dc = "http://purl.org/dc/elements/1.1/"
        for key, value in (("title", spec.get("title", "Paperclay presentation")), ("creator", spec.get("author", ""))):
            node = core.find("{" + dc + "}" + key)
            if node is None:
                node = ET.SubElement(core, "{" + dc + "}" + key)
            node.text = str(value)
        parts["docProps/core.xml"] = xml_bytes(core)
    if "docProps/app.xml" in parts:
        app = ET.fromstring(parts["docProps/app.xml"])
        for node in app.iter():
            if node.tag.endswith("}Slides"):
                node.text = str(len(report))
        parts["docProps/app.xml"] = xml_bytes(app)
    write_package(parts, output)
    return {"output": str(output), "slides": len(report), "images": media_number, "charts": chart_number, "layouts": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="JSON content plan; image paths are relative to this file")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template", type=Path, default=ASSETS / "paperclay.pptx")
    parser.add_argument("--catalog", type=Path, help="Defaults to layouts.json next to the template")
    parser.add_argument("--allow-overflow", action="store_true", help="Warn instead of refusing text above the layout's character guide")
    args = parser.parse_args()
    try:
        result = compose(args.spec, args.output, args.template, args.catalog, args.allow_overflow)
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
