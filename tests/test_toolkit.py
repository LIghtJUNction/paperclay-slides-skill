"""Run with: python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_deck import audit
from compose_deck import compose
from inspect_template import inspect
from ooxml import NS, ordered_slides, read_package, shape_bounds, shape_key, shape_text


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes((204, 130, 100)) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paperclay-test-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, slides, **kwargs):
        spec = self.directory / "deck.json"
        spec.write_text(json.dumps({"title": "Toolkit test", "footer": "Example", "slides": slides}), encoding="utf-8")
        output = self.directory / "deck.pptx"
        compose(spec, output, **kwargs)
        return output

    def test_repeated_layouts_have_independent_text_and_notes(self):
        output = self.build([{"layout": "cover", "text": {"title": "第一张"}, "notes": "Source one"}, {"layout": "cover", "text": {"title": "第二张"}, "notes": "Source two"}])
        parts = read_package(output)
        self.assertEqual(len(ordered_slides(parts)), 2)
        first = ET.fromstring(parts["ppt/slides/slide1.xml"])
        second = ET.fromstring(parts["ppt/slides/slide2.xml"])
        self.assertIn("第一张", "".join(first.itertext()))
        self.assertNotIn("第二张", "".join(first.itertext()))
        self.assertIn("第二张", "".join(second.itertext()))
        self.assertIn(b"Source one", parts["ppt/notesSlides/notesSlide1.xml"])
        self.assertIn(b"Source two", parts["ppt/notesSlides/notesSlide2.xml"])
        self.assertTrue(audit(output)["ok"])

    def test_missing_optional_fields_leave_no_guide_text(self):
        output = self.build([{"layout": "cover", "text": {"title": "已填标题"}}])
        parts = read_package(output)
        for name, data in parts.items():
            if (name.startswith("ppt/slides/") or name.startswith("ppt/slideLayouts/")) and name.endswith(".xml"):
                self.assertNotIn("[", "".join(ET.fromstring(data).itertext()), name)

    def test_bad_keys_and_title_capacity_fail(self):
        for entry, expected in (({"layout": "cover", "text": {"title": "标题", "typo": "bad"}}, "Unknown field"), ({"layout": "cover", "text": {"title": "长" * 31}}, "character"), ({"layout": "missing", "text": {}}, "unknown layout")):
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, expected):
                self.build([entry])

    def test_native_picture_keeps_aspect_ratio(self):
        (self.directory / "photo.png").write_bytes(png(200, 100))
        output = self.build([{"layout": "cover", "text": {"title": "图片"}, "images": {"image_1": {"path": "photo.png", "fit": "contain"}, "image_2": {"path": "photo.png", "fit": "cover"}}}])
        root = ET.fromstring(read_package(output)["ppt/slides/slide1.xml"])
        pictures = root.findall("p:cSld/p:spTree/p:pic", NS)
        self.assertEqual(len(pictures), 2)
        _, _, width, height = shape_bounds(pictures[0])
        self.assertAlmostEqual(width / height, 2, places=5)
        self.assertGreater(int(pictures[1].find("p:blipFill/a:srcRect", NS).get("l", 0)), 0)

    def test_table_and_chart_are_native_and_embedded(self):
        output = self.build([{"layout": "native_table", "text": {"title": "对比"}, "tables": {"table": {"headers": ["项目", "数值"], "rows": [["甲", 10], ["乙", 20]]}}}, {"layout": "chart_full", "text": {"title": "数据"}, "charts": {"chart": {"type": "bar", "categories": ["A", "B"], "series": [{"name": "样例", "values": [1, 2]}]}}}, {"layout": "chart_full", "text": {"title": "趋势"}, "charts": {"chart": {"type": "line", "categories": ["A", "B"], "series": [{"name": "样例", "values": [2, 1]}]}}}])
        parts = read_package(output)
        self.assertEqual(len(ET.fromstring(parts["ppt/slides/slide1.xml"]).findall(".//a:tbl", NS)), 1)
        self.assertEqual(len([name for name in parts if name.startswith("ppt/embeddings/paperclay-chart-") and name.endswith(".xlsx")]), 2)
        report = audit(output)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["objects"]["charts"], 2)

    def test_team_portrait_keeps_circular_mask(self):
        (self.directory / "avatar.png").write_bytes(png(200, 100))
        output = self.build([{"layout": "team", "text": {"title": "团队"}, "images": {"image_1": {"path": "avatar.png", "fit": "cover"}}}])
        root = ET.fromstring(read_package(output)["ppt/slides/slide1.xml"])
        picture = root.find("p:cSld/p:spTree/p:pic", NS)
        self.assertEqual(picture.find("p:spPr/a:prstGeom", NS).get("prst"), "ellipse")

    def test_table_and_chart_dimension_mismatch_fail(self):
        for entry in ({"layout": "native_table", "text": {"title": "错误表格"}, "tables": {"table": {"headers": ["A", "B"], "rows": [[1]]}}}, {"layout": "chart_full", "text": {"title": "错误图表"}, "charts": {"chart": {"categories": ["A", "B"], "series": [{"name": "Series", "values": [1]}]}}}):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.build([entry])

    def test_inspector_resolves_inherited_bounds(self):
        report = inspect(ROOT / "assets/paperclay.pptx", "cover")
        title = next(item for item in report["layouts"][0]["placeholders"] if item["key"] == "title")
        self.assertEqual(title["bounds_px"]["x"], 64)
        self.assertEqual(title["native_type"], "title")


if __name__ == "__main__":
    unittest.main()
