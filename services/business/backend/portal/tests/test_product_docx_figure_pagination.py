import io
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from django.test import SimpleTestCase

from portal.product_docx_layout import normalize_docx_layout
from portal.tests import test_product_documents as fixtures


class FigurePaginationTests(SimpleTestCase):
    def test_image_caption_stay_together_without_chaining_explanation_or_next_section(self):
        fixture = fixtures.GeneratedWordLayoutTests()
        source = fixture.xml().replace(
            b'<w:p><w:pPr><w:keepNext/></w:pPr><w:r><w:drawing>',
            b'<w:p><w:pPr><w:keepNext/></w:pPr><w:r><w:t>Explanation</w:t></w:r></w:p>'
            b'<w:p><w:pPr><w:keepNext w:val="0"/></w:pPr><w:r><w:drawing>',
        ).replace(
            b'<w:p><w:r><w:t>Caption and retained note</w:t><w:br w:type="page"/></w:r></w:p>',
            '<w:p><w:pPr><w:keepNext/></w:pPr><w:r><w:t>图 1.1 完整流程</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Following text</w:t></w:r></w:p>'.encode(),
        )
        original = fixture.package(source)
        normalized, evidence = normalize_docx_layout(original, ["H1"])
        with ZipFile(io.BytesIO(normalized)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            self.assertEqual(archive.read("word/media/image1.png"), b"exact raster bytes")
        w = fixture.W
        paragraphs = root.findall(f"{w}body/{w}p")
        image = next(p for p in paragraphs if p.find(f".//{w}drawing") is not None)
        position = paragraphs.index(image)
        explanation, caption = paragraphs[position - 1], paragraphs[position + 1]
        for paragraph, keep_next in ((explanation, "0"), (image, "1"), (caption, "0")):
            self.assertEqual(paragraph.find(f"{w}pPr/{w}keepNext").get(w + "val"), keep_next)
        for paragraph in (image, caption):
            self.assertEqual(paragraph.find(f"{w}pPr/{w}keepLines").get(w + "val"), "1")
            self.assertIsNone(paragraph.find(f"{w}pPr/{w}pageBreakBefore"))
        self.assertFalse(root.findall(f".//{w}br"))
        self.assertEqual(evidence["atomic_figure_count"], 1)
        repeated, _ = normalize_docx_layout(normalized, ["H1"])
        self.assertEqual(repeated, normalized)
