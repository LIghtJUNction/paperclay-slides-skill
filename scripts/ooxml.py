"""Small, standard-library OOXML helpers for Paperclay Slides."""
from __future__ import annotations

import copy
import io
import json
import math
import posixpath
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
for _prefix in ("p", "a", "r", "c"):
    ET.register_namespace(_prefix, NS[_prefix])

REL = NS["r"] + "/"
EMU = 9525  # one CSS pixel at 96 dpi
PALETTE = {"paper": "F6F2EC", "ink": "0A0A09", "muted": "77756E", "clay": "E07852", "blue": "BED2E4", "teal": "62A08F", "stone": "E4E1D5", "peach": "EDC9B6", "line": "C8C5BC"}
FONT = "Noto Sans CJK SC"
_tokens_path = Path(__file__).resolve().parent.parent / "assets/tokens.json"
if _tokens_path.exists():
    _tokens = json.loads(_tokens_path.read_text(encoding="utf-8"))
    PALETTE.update({key: value.lstrip("#") for key, value in _tokens.get("colors", {}).items()})
    FONT = _tokens.get("fonts", {}).get("sans", FONT)
COLORS = [PALETTE[key] for key in ("clay", "blue", "teal", "muted", "stone", "peach")]


def tag(name: str) -> str:
    prefix, local = name.split(":")
    return "{" + NS[prefix] + "}" + local


def el(name: str, attrs: dict | None = None, parent=None, text=None):
    value = ET.Element(tag(name), {k: str(v) for k, v in (attrs or {}).items()})
    if text is not None:
        value.text = str(text)
    if parent is not None:
        parent.append(value)
    return value


def xml_bytes(root) -> bytes:
    # OPC readers such as LibreOffice expect the package-level schemas as a
    # default namespace even though prefixed forms are XML-equivalent.
    for namespace in (NS["ct"], NS["pr"], NS["s"]):
        if root.tag.startswith("{" + namespace + "}"):
            ET.register_namespace("", namespace)
            break
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def read_package(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError("The PowerPoint ZIP package is damaged")
        return {name: archive.read(name) for name in archive.namelist()}


def write_package(parts: dict[str, bytes], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(parts.items()):
            archive.writestr(name, data)


def rels_path(part: str) -> str:
    directory, basename = posixpath.split(part)
    return posixpath.join(directory, "_rels", basename + ".rels")


def resolve_target(part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def relationships(parts, part):
    name = rels_path(part)
    return ET.fromstring(parts[name]) if name in parts else el("pr:Relationships")


def add_rel(root, kind, target, external=False):
    occupied = {item.get("Id") for item in root}
    number = 1
    while "rId" + str(number) in occupied:
        number += 1
    rid = "rId" + str(number)
    attrs = {"Id": rid, "Type": REL + kind, "Target": target}
    if external:
        attrs["TargetMode"] = "External"
    el("pr:Relationship", attrs, root)
    return rid


def ordered_slides(parts):
    relmap = {item.get("Id"): item.get("Target") for item in relationships(parts, "ppt/presentation.xml")}
    root = ET.fromstring(parts["ppt/presentation.xml"])
    ids = root.find("p:sldIdLst", NS)
    if ids is None:
        return []
    return [resolve_target("ppt/presentation.xml", relmap[item.get(tag("r:id"))]) for item in ids]


def shape_name(shape):
    node = shape.find(".//p:cNvPr", NS)
    return node.get("name", "") if node is not None else ""


def shape_key(shape):
    name = shape_name(shape)
    return name[3:] if name.startswith("ph:") else None


def shape_bounds(shape):
    xfrm = shape.find("p:spPr/a:xfrm", NS)
    if xfrm is None:
        xfrm = shape.find("p:xfrm", NS)
    if xfrm is None:
        return None
    offset, extent = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if offset is None or extent is None:
        return None
    return tuple(int(node.get(k, 0)) for node, k in ((offset, "x"), (offset, "y"), (extent, "cx"), (extent, "cy")))


def inherit_geometry(parts, slide, slide_part):
    """Materialize a placeholder's layout geometry when the slide inherits it."""
    relation = next((item for item in relationships(parts, slide_part) if item.get("Type") == REL + "slideLayout"), None)
    if relation is None:
        return
    layout_part = resolve_target(slide_part, relation.get("Target"))
    layout = ET.fromstring(parts[layout_part])
    layout_shapes = layout.findall("p:cSld/p:spTree/*", NS)
    for shape in slide.findall("p:cSld/p:spTree/*", NS):
        if shape_bounds(shape):
            continue
        ph = shape.find(".//p:ph", NS)
        if ph is None:
            continue
        match = None
        for candidate in layout_shapes:
            other = candidate.find(".//p:ph", NS)
            if other is not None and other.get("idx", "0") == ph.get("idx", "0"):
                match = candidate
                break
        if match is None:
            continue
        inherited = match.find("p:spPr/a:xfrm", NS)
        if inherited is not None:
            props = shape.find("p:spPr", NS)
            if props is not None:
                props.insert(0, copy.deepcopy(inherited))


def shape_text(shape):
    return "\n".join("".join(p.itertext()) for p in shape.findall("p:txBody/a:p", NS))


def set_text(shape, value):
    body = shape.find("p:txBody", NS)
    if body is None:
        raise ValueError("Text target has no text body: " + shape_name(shape))
    paragraph = body.find("a:p", NS)
    ppr = paragraph.find("a:pPr", NS) if paragraph is not None else None
    rpr = body.find(".//a:rPr", NS)
    if rpr is None and ppr is not None:
        rpr = ppr.find("a:defRPr", NS)
    for old in list(body):
        if old.tag == tag("a:p"):
            body.remove(old)
    for line in str(value).split("\n"):
        p = el("a:p", parent=body)
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        if line:
            run = el("a:r", parent=p)
            if rpr is not None:
                style = copy.deepcopy(rpr)
                style.tag = tag("a:rPr")
                run.append(style)
            el("a:t", parent=run, text=line)
        end = copy.deepcopy(rpr) if rpr is not None else el("a:endParaRPr")
        end.tag = tag("a:endParaRPr")
        p.append(end)


def add_override(types, part, mime):
    name = "/" + part
    old = next((item for item in types if item.get("PartName") == name), None)
    if old is None:
        el("ct:Override", {"PartName": name, "ContentType": mime}, types)
    else:
        old.set("ContentType", mime)


def add_default(types, extension, mime):
    if not any(item.get("Extension", "").lower() == extension.lower() for item in types):
        el("ct:Default", {"Extension": extension, "ContentType": mime}, types)


def image_size(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return (*struct.unpack(">II", data[16:24]), "png", "image/png")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return (*struct.unpack("<HH", data[6:10]), "gif", "image/gif")
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index < len(data):
            while index < len(data) and data[index] == 255:
                index += 1
            if index >= len(data):
                break
            marker = data[index]
            index += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            length = struct.unpack(">H", data[index:index + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[index + 3:index + 7])
                return width, height, "jpg", "image/jpeg"
            index += length
    raise ValueError("Supported image formats are PNG, JPEG, and GIF")


def copy_nonvisual(shape, parent, kind):
    source = shape.find(".//p:cNvPr", NS)
    parent.append(copy.deepcopy(source) if source is not None else el("p:cNvPr", {"id": 100, "name": "object"}))
    el("p:" + kind, parent=parent)
    nv = shape.find(".//p:nvPr", NS)
    parent.append(copy.deepcopy(nv) if nv is not None else el("p:nvPr"))


def transform(parent, bounds, tag_name="a:xfrm"):
    x, y, w, h = bounds
    xfrm = el(tag_name, parent=parent)
    el("a:off", {"x": x, "y": y}, xfrm)
    el("a:ext", {"cx": w, "cy": h}, xfrm)
    return xfrm


def make_picture(shape, rid, width, height, fit):
    bounds = shape_bounds(shape)
    if not bounds or not all(value > 0 for value in (bounds[2], bounds[3], width, height)):
        raise ValueError("Picture placeholder has invalid bounds")
    x, y, w, h = bounds
    box_ratio, image_ratio = w / h, width / height
    picture = el("p:pic")
    nv = el("p:nvPicPr", parent=picture)
    copy_nonvisual(shape, nv, "cNvPicPr")
    el("a:picLocks", {"noChangeAspect": 1}, nv.find("p:cNvPicPr", NS))
    blipfill = el("p:blipFill", parent=picture)
    el("a:blip", {tag("r:embed"): rid}, blipfill)
    crop = {}
    if fit == "cover":
        if image_ratio > box_ratio:
            cut = round((1 - box_ratio / image_ratio) * 50000)
            crop = {"l": cut, "r": cut}
        else:
            cut = round((1 - image_ratio / box_ratio) * 50000)
            crop = {"t": cut, "b": cut}
    elif fit == "contain":
        if image_ratio > box_ratio:
            new_h = round(w / image_ratio)
            y += (h - new_h) // 2
            h = new_h
        else:
            new_w = round(h * image_ratio)
            x += (w - new_w) // 2
            w = new_w
    else:
        raise ValueError("Image fit must be 'cover' or 'contain'")
    el("a:srcRect", crop, blipfill)
    el("a:fillRect", parent=el("a:stretch", parent=blipfill))
    props = el("p:spPr", parent=picture)
    transform(props, (x, y, w, h))
    geometry = shape.find("p:spPr/a:prstGeom", NS)
    if geometry is not None:
        props.append(copy.deepcopy(geometry))
    else:
        el("a:avLst", parent=el("a:prstGeom", {"prst": "rect"}, props))
    return picture


def font_props(parent, size, bold=False, color=None, name="a:defRPr"):
    rp = el(name, {"sz": size, "b": int(bold)}, parent)
    el("a:srgbClr", {"val": color or PALETTE["ink"]}, el("a:solidFill", parent=rp))
    el("a:latin", {"typeface": FONT}, rp)
    el("a:ea", {"typeface": FONT}, rp)
    return rp


def make_frame(shape, uri):
    frame = el("p:graphicFrame")
    nv = el("p:nvGraphicFramePr", parent=frame)
    copy_nonvisual(shape, nv, "cNvGraphicFramePr")
    transform(frame, shape_bounds(shape), "p:xfrm")
    data = el("a:graphicData", {"uri": uri}, el("a:graphic", parent=frame))
    return frame, data


def make_table(shape, headers, rows):
    if not headers or not isinstance(headers, list):
        raise ValueError("A table needs non-empty headers")
    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        raise ValueError("Every table row must have the same length as headers")
    frame, data = make_frame(shape, "http://schemas.openxmlformats.org/drawingml/2006/table")
    table = el("a:tbl", parent=data)
    el("a:tblPr", {"firstRow": 1, "bandRow": 0}, table)
    grid = el("a:tblGrid", parent=table)
    _, _, width, height = shape_bounds(shape)
    count = len(headers)
    widths = [round(width / count)] * count
    widths[-1] = width - sum(widths[:-1])
    for value in widths:
        el("a:gridCol", {"w": value}, grid)
    all_rows = [headers] + rows
    row_height = height // len(all_rows)
    # Keep labels at the reference's readable scale; reject excessively dense data.
    if row_height < 250000:
        raise ValueError("Too many table rows for this placeholder; split the table across slides")
    size = min(1600, max(1100, round(row_height / 12700 * 45)))
    for index, row in enumerate(all_rows):
        tr = el("a:tr", {"h": row_height if index < len(all_rows) - 1 else height - row_height * index}, table)
        for column, value in enumerate(row):
            cell = el("a:tc", parent=tr)
            body = el("a:txBody", parent=cell)
            el("a:bodyPr", {"anchor": "ctr"}, body)
            el("a:lstStyle", parent=body)
            for line in str(value).split("\n"):
                p = el("a:p", parent=body)
                ppr = el("a:pPr", {"algn": "l" if column == 0 else "ctr"}, p)
                font_props(ppr, size, index == 0)
                run = el("a:r", parent=p)
                font_props(run, size, index == 0, name="a:rPr")
                el("a:t", parent=run, text=line)
            props = el("a:tcPr", {"marL": 90000, "marR": 90000, "marT": 45000, "marB": 45000, "anchor": "ctr"}, cell)
            el("a:srgbClr", {"val": PALETTE["stone"] if index == 0 else PALETTE["paper"]}, el("a:solidFill", parent=props))
            for side in ("L", "R", "T"):
                el("a:noFill", parent=el("a:ln" + side, {"w": 0}, props))
            bottom = el("a:lnB", {"w": 6350}, props)
            el("a:srgbClr", {"val": PALETTE["line"]}, el("a:solidFill", parent=bottom))
    return frame


def column_name(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def make_workbook(categories, series):
    types = el("ct:Types")
    add_default(types, "rels", "application/vnd.openxmlformats-package.relationships+xml")
    add_default(types, "xml", "application/xml")
    add_override(types, "xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    add_override(types, "xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    wb = el("s:workbook")
    el("s:sheet", {"name": "Sheet1", "sheetId": 1, tag("r:id"): "rId1"}, el("s:sheets", parent=wb))
    rootrels = el("pr:Relationships")
    add_rel(rootrels, "officeDocument", "xl/workbook.xml")
    wbrels = el("pr:Relationships")
    add_rel(wbrels, "worksheet", "worksheets/sheet1.xml")
    sheet = el("s:worksheet")
    sheetdata = el("s:sheetData", parent=sheet)
    values = [["Category"] + [item["name"] for item in series]]
    values += [[category] + [item["values"][index] for item in series] for index, category in enumerate(categories)]
    for row_number, values_row in enumerate(values, 1):
        row = el("s:row", {"r": row_number}, sheetdata)
        for col, value in enumerate(values_row, 1):
            numeric = row_number > 1 and col > 1
            cell = el("s:c", {"r": column_name(col) + str(row_number), "t": "n" if numeric else "inlineStr"}, row)
            if numeric:
                el("s:v", parent=cell, text=value)
            else:
                el("s:t", parent=el("s:is", parent=cell), text=value)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, root in {"[Content_Types].xml": types, "_rels/.rels": rootrels, "xl/workbook.xml": wb, "xl/_rels/workbook.xml.rels": wbrels, "xl/worksheets/sheet1.xml": sheet}.items():
            archive.writestr(name, xml_bytes(root))
    return output.getvalue()


def chart_text(parent, size=1100):
    tx = el("c:txPr", parent=parent)
    el("a:bodyPr", parent=tx)
    el("a:lstStyle", parent=tx)
    p = el("a:p", parent=tx)
    font_props(el("a:pPr", parent=p), size, color=PALETTE["muted"])
    el("a:endParaRPr", {"lang": "zh-CN"}, p)


def cache(parent, kind, formula, values):
    ref = el("c:" + kind + "Ref", parent=parent)
    el("c:f", parent=ref, text=formula)
    cached = el("c:" + kind + "Cache", parent=ref)
    if kind == "num":
        el("c:formatCode", parent=cached, text="General")
    el("c:ptCount", {"val": len(values)}, cached)
    for index, value in enumerate(values):
        el("c:v", parent=el("c:pt", {"idx": index}, cached), text=value)


def make_chart(shape, config, chart_rid):
    kind = config.get("type", "bar")
    categories, series = config.get("categories"), config.get("series")
    if kind not in ("bar", "line"):
        raise ValueError("Supported chart types are 'bar' and 'line'")
    if not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
        raise ValueError("A chart needs non-empty categories and series")
    for item in series:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or len(item.get("values", [])) != len(categories):
            raise ValueError("Each chart series needs a name and one value per category")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in item["values"]):
            raise ValueError("Chart values must be finite numbers")
    frame, data = make_frame(shape, NS["c"])
    el("c:chart", {tag("r:id"): chart_rid}, data)
    space = el("c:chartSpace")
    el("c:date1904", {"val": 0}, space)
    el("c:lang", {"val": "zh-CN"}, space)
    chart = el("c:chart", parent=space)
    el("c:autoTitleDeleted", {"val": 1}, chart)
    plot = el("c:plotArea", parent=chart)
    el("c:layout", parent=plot)
    graph = el("c:" + kind + "Chart", parent=plot)
    if kind == "bar":
        el("c:barDir", {"val": "col"}, graph)
    el("c:grouping", {"val": "clustered" if kind == "bar" else "standard"}, graph)
    el("c:varyColors", {"val": 0}, graph)
    for index, item in enumerate(series):
        ser = el("c:ser", parent=graph)
        el("c:idx", {"val": index}, ser)
        el("c:order", {"val": index}, ser)
        column = column_name(index + 2)
        cache(el("c:tx", parent=ser), "str", f"Sheet1!${column}$1", [item["name"]])
        props = el("c:spPr", parent=ser)
        color = item.get("color", COLORS[index % len(COLORS)]).lstrip("#")
        if len(color) != 6 or any(c not in "0123456789abcdefABCDEF" for c in color):
            raise ValueError("Chart series color must be a six-digit hex color")
        if kind == "bar":
            el("a:srgbClr", {"val": color}, el("a:solidFill", parent=props))
            el("a:noFill", parent=el("a:ln", parent=props))
        else:
            el("a:srgbClr", {"val": color}, el("a:solidFill", parent=el("a:ln", {"w": 25400}, props)))
            marker = el("c:marker", parent=ser)
            el("c:symbol", {"val": "circle"}, marker)
            el("c:size", {"val": 4}, marker)
        cache(el("c:cat", parent=ser), "str", f"Sheet1!$A$2:$A${len(categories) + 1}", categories)
        cache(el("c:val", parent=ser), "num", f"Sheet1!${column}$2:${column}${len(categories) + 1}", item["values"])
        if kind == "line":
            el("c:smooth", {"val": 0}, ser)
    labels = el("c:dLbls", parent=graph)
    chart_text(labels, 1100)
    el("c:showLegendKey", {"val": 0}, labels)
    el("c:showVal", {"val": int(bool(config.get("show_values", kind == "bar")))}, labels)
    el("c:showCatName", {"val": 0}, labels)
    el("c:showSerName", {"val": 0}, labels)
    el("c:showPercent", {"val": 0}, labels)
    el("c:showBubbleSize", {"val": 0}, labels)
    if kind == "bar":
        el("c:gapWidth", {"val": 70}, graph)
        el("c:overlap", {"val": 0}, graph)
    for axisid in (246001, 246002):
        el("c:axId", {"val": axisid}, graph)
    for axis_kind, axisid, other, position in (("catAx", 246001, 246002, "b"), ("valAx", 246002, 246001, "l")):
        axis = el("c:" + axis_kind, parent=plot)
        el("c:axId", {"val": axisid}, axis)
        el("c:orientation", {"val": "minMax"}, el("c:scaling", parent=axis))
        el("c:delete", {"val": 0}, axis)
        el("c:axPos", {"val": position}, axis)
        if axis_kind == "valAx":
            grid = el("c:majorGridlines", parent=axis)
            el("a:srgbClr", {"val": PALETTE["line"]}, el("a:solidFill", parent=el("a:ln", {"w": 6350}, el("c:spPr", parent=grid))))
            el("c:numFmt", {"formatCode": "General", "sourceLinked": 0}, axis)
        el("c:majorTickMark", {"val": "none"}, axis)
        el("c:minorTickMark", {"val": "none"}, axis)
        el("c:tickLblPos", {"val": "nextTo"}, axis)
        props = el("c:spPr", parent=axis)
        el("a:srgbClr", {"val": PALETTE["muted"]}, el("a:solidFill", parent=el("a:ln", {"w": 6350}, props)))
        chart_text(axis)
        el("c:crossAx", {"val": other}, axis)
        el("c:crosses", {"val": "autoZero"}, axis)
        if axis_kind == "catAx":
            el("c:auto", {"val": 1}, axis)
            el("c:lblAlgn", {"val": "ctr"}, axis)
            el("c:lblOffset", {"val": 100}, axis)
        else:
            el("c:crossBetween", {"val": "between"}, axis)
    if len(series) > 1:
        legend = el("c:legend", parent=chart)
        el("c:legendPos", {"val": "b"}, legend)
        el("c:layout", parent=legend)
        el("c:overlay", {"val": 0}, legend)
        chart_text(legend)
    el("c:plotVisOnly", {"val": 1}, chart)
    el("c:dispBlanksAs", {"val": "gap"}, chart)
    props = el("c:spPr", parent=space)
    el("a:noFill", parent=props)
    el("a:noFill", parent=el("a:ln", parent=props))
    chart_text(space)
    el("c:autoUpdate", {"val": 0}, el("c:externalData", {tag("r:id"): "rId1"}, space))
    return frame, xml_bytes(space), make_workbook(categories, series)
