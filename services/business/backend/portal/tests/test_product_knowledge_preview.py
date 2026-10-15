"""Representative original-file checks; runner denies all real network calls."""
from html import escape
from io import BytesIO
import json
import struct
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from portal import product_knowledge_api as api
from portal import product_knowledge_service as service
from portal.product_knowledge_preview import FILE_LIMIT
from .base import PortalTestCase
from .intake_fixtures import docx, package, pdf
from .test_product_knowledge_documents import CONFIG, URL, ProviderResponse, document, wire_documents


class OriginalResponse(ProviderResponse):
    def __init__(self, raw, **kwargs):
        super().__init__(raw, **kwargs)
        self.headers = {"Content-Length": str(len(raw))}


class ProductKnowledgePreviewTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("original-reader", "product")
        self.user.refresh_from_db()
        self.grants = {str(self.user.pk): {"dataset-05": ["doc-a"]}}
        settings = override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS=self.grants,
                                     PRODUCT_KNOWLEDGE_URL=URL)
        settings.enable()
        self.addCleanup(settings.disable)
        configuration = patch.object(service, "configuration", return_value=CONFIG)
        self.configuration = configuration.start()
        self.addCleanup(configuration.stop)
        self.factory = APIRequestFactory()
        with service._original_cache_lock:
            service._original_cache.clear()
        self.addCleanup(service._original_cache.clear)

    def request(self, view=api.document_preview, **kwargs):
        request = self.factory.get("/api/product/knowledge/datasets/dataset-05/documents/doc-a/preview/" +
                                   kwargs.pop("query", ""))
        force_authenticate(request, user=self.user)
        response = view(request, dataset_id="dataset-05", document_id=kwargs.pop("document_id", "doc-a"))
        if hasattr(response, "render"):
            response.render()
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def provider(self, raw, name, **kwargs):
        return patch.object(service, "_open", side_effect=[
            ProviderResponse(wire_documents([document("doc-a", name, size=len(raw))])),
            OriginalResponse(raw, **kwargs)])

    def test_pdf_and_download_return_identical_original_bytes_without_chunks(self):
        import fitz
        with fitz.open() as source:
            for index in range(7):
                page = source.new_page(width=120, height=160)
                page.insert_text((10, 30), "PAGE " + str(index + 1))
            raw = source.tobytes()
        metadata = wire_documents([document("doc-a", "完整文档.pdf", size=len(raw))])
        with self.provider(raw, "完整文档.pdf"), patch.object(service, "list_chunks", side_effect=AssertionError("chunks")):
            response = self.request()
        manifest = json.loads(response.content)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(manifest["kind"], "pdf")
        self.assertEqual([page["page"] for page in manifest["pages"]], list(range(1, 8)))
        for start, expected, following in ((1, [1, 2, 3], 4), (4, [4, 5, 6], 7), (7, [7], None)):
            with self.subTest(start=start), patch.object(service, "_open", return_value=ProviderResponse(metadata)) as provider, patch.object(
                    service, "list_chunks", side_effect=AssertionError("chunks")):
                result = self.request(api.document_pages, query="?start_page=" + str(start)).data
            self.assertEqual(provider.call_count, 1)  # Fresh metadata, original bytes from cache.
            self.assertEqual(result["kind"], "pdf_pages")
            self.assertEqual(result["page_count"], 7)
            self.assertEqual([page["page"] for page in result["pages"]], expected)
            self.assertEqual(result["next_page"], following)
            for page in result["pages"]:
                self.assertEqual((page["width"], page["height"]), (120, 160))
                self.assertTrue(page["image"].startswith("data:image/jpeg;base64,"))
        with self.provider(raw, "完整文档.pdf") as provider:
            downloaded = self.request(api.document_download)
        self.assertEqual(provider.call_count, 2)  # Download always retrieves the fresh original.
        self.assertEqual(downloaded["Content-Type"], "application/octet-stream")
        self.assertEqual(downloaded.content, raw)
        self.assertEqual(downloaded["Content-Length"], str(len(raw)))
        self.assertEqual(downloaded["X-Content-Type-Options"], "nosniff")
        self.assertEqual(parse_qs(urlsplit(provider.call_args_list[0].args[0].full_url).query),
                         {"id": ["doc-a"], "page": ["1"], "page_size": ["1"]})
        self.assertEqual(provider.call_args_list[1].args[0].full_url,
                         URL.removesuffix("retrieval") + "datasets/dataset-05/documents/doc-a")
        with patch.object(service, "_open", return_value=ProviderResponse(metadata)), patch("portal.product_knowledge_preview.HTML_LIMIT", 512):
            rejected = self.request(api.document_pages)
        self.assertEqual(rejected.status_code, 413)
        self.assertEqual(rejected.data["code"], "preview_limit")

    def test_pdf_manifest_over_200_pages_lists_every_page_without_rendering(self):
        import fitz
        with fitz.open() as source:
            for _ in range(205):
                source.new_page(width=120, height=160)
            raw = source.tobytes()
        with self.provider(raw, "长文.pdf"), patch.object(fitz.Page, "get_pixmap", side_effect=AssertionError("manifest must not render")):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        manifest = json.loads(response.content)
        self.assertEqual(manifest["page_count"], 205)
        self.assertEqual(manifest["kind"], "pdf")
        self.assertEqual(manifest["pages"], [{"page": page, "width": 120.0, "height": 160.0} for page in range(1, 206)])

    def test_preview_original_cache_checks_metadata_version_configuration_ttl_and_byte_bound(self):
        row = document("doc-a", "原件.pdf", size=3, update_date="version-one")
        fingerprints = []
        for update in ("version-one", "version-two"):
            with patch.object(service, "_open", return_value=ProviderResponse(wire_documents([{**row, "update_date": update}]))):
                fingerprints.append(service.original_document_metadata("dataset-05", "doc-a", CONFIG))
        self.assertNotEqual(fingerprints[0]["fingerprint"], fingerprints[1]["fingerprint"])
        changed = (URL, "new-config-token", CONFIG[2])
        with patch.object(service, "original_document", side_effect=[b"one", b"two", b"new", b"ttl", b"end"]) as read, patch.object(
                service, "monotonic", return_value=100) as clock:
            def cached(metadata=fingerprints[0], config=CONFIG):
                return service.cached_original_document("dataset-05", "doc-a", metadata, config)
            self.assertEqual(cached(), b"one")
            self.assertEqual(cached(), b"one")
            self.assertEqual(read.call_count, 1)
            self.assertEqual(cached(fingerprints[1]), b"two")
            self.assertEqual(cached(fingerprints[1], changed), b"new")
            self.assertEqual(read.call_count, 3)
            clock.return_value = 221
            self.assertEqual(cached(fingerprints[1], changed), b"ttl")
            self.assertEqual(read.call_count, 4)
            with patch.object(service, "ORIGINAL_CACHE_LIMIT", 4):
                self.assertEqual(cached(), b"end")
                self.assertLessEqual(sum(len(value[1]) for value in service._original_cache.values()), 4)
                self.assertEqual(len(service._original_cache), 1)

    def test_pdf_page_parameters_and_revocation_during_read_or_render_fail_closed(self):
        with patch.object(service, "_open") as provider:
            for query in ("?start_page=0", "?start_page=1&start_page=2", "?page_size=6", "?page_size=0",
                          "?start_page=1.5", "?page_size=3&page_size=3", "?unknown=1", "?start_page=" + "1" * 5000):
                self.assertEqual(self.request(api.document_pages, query=query).status_code, 400)
            self.assertEqual(self.request(api.document_pages, document_id="hidden").status_code, 404)
        provider.assert_not_called()
        raw = pdf("PRIVATE ORIGINAL")
        with self.provider(raw, "原件.pdf"):
            out_of_range = self.request(api.document_pages, query="?start_page=2")
        self.assertEqual(out_of_range.status_code, 400)
        with service._original_cache_lock:
            service._original_cache.clear()
        def revoke():
            self.grants[str(self.user.pk)] = {"dataset-05": ["other"]}
        with self.provider(raw, "原件.pdf", on_read=revoke):
            rejected = self.request(api.document_pages)
        self.assertEqual(rejected.status_code, 403)
        self.assertNotIn(b"data:image", rejected.content)
        self.grants[str(self.user.pk)] = {"dataset-05": ["doc-a"]}
        import fitz
        render = fitz.Page.get_pixmap
        def render_and_revoke(page, *args, **kwargs):
            revoke()
            return render(page, *args, **kwargs)
        metadata = wire_documents([document("doc-a", "原件.pdf", size=len(raw))])
        with patch.object(service, "_open", return_value=ProviderResponse(metadata)), patch.object(fitz.Page, "get_pixmap", render_and_revoke):
            rejected = self.request(api.document_pages)
        self.assertEqual(rejected.status_code, 403)
        self.assertNotIn(b"data:image", rejected.content)

    def test_path_prefixed_name_is_display_only_and_disposition_uses_safe_basename(self):
        raw = docx("授权原件完整首尾内容")
        for name in ("01_产品事业部_方案与可研库_General/项目可行性研究报告.docx", "知识库\\项目可行性研究报告.docx",
                     "../../项目可行性研究报告.docx"):
            for view in (api.document_preview, api.document_download):
                with self.subTest(name=name, view=view.__name__), self.provider(raw, name) as provider:
                    response = self.request(view)
                self.assertEqual(response.status_code, 200)
                header = unquote(response["Content-Disposition"])
                self.assertIn("项目可行性研究报告.docx", header)
                self.assertNotIn("/", header)
                self.assertNotIn("\\", header)
                self.assertNotIn("General", header)
                if view == api.document_preview:
                    self.assertIn(escape(name), response.content.decode())
                    self.assertIn("授权原件完整首尾内容", response.content.decode())
                else:
                    self.assertEqual(response.content, raw)
                for call in provider.call_args_list:
                    parsed = urlsplit(call.args[0].full_url)
                    self.assertEqual(parsed.hostname, urlsplit(URL).hostname)
                    self.assertIn("/datasets/dataset-05/documents", parsed.path)
                    self.assertNotIn("General", call.args[0].full_url)
        for name in ("知识库/原件\r\nInjected: bad.docx", "知识库/原件\x00.docx", "知识库/", "知识库\\.."):
            with self.subTest(invalid_name=name), self.provider(raw, name) as provider:
                rejected = self.request(api.document_download)
            self.assertEqual(rejected.status_code, 502)
            self.assertEqual(provider.call_count, 1)

    def test_docx_complete_body_tables_header_footer_notes_textboxes_and_passive_images(self):
        namespace = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        def paragraph(value):
            return '<w:p><w:r><w:t>' + escape(value) + '</w:t></w:r></w:p>'
        body = ''.join(paragraph(f"正文完整序号{i}尾文") for i in range(160))
        body += '<w:tbl><w:tr><w:tc>' + paragraph("表格最终单元格") + '</w:tc></w:tr></w:tbl>'
        body += '<w:hyperlink r:id="external">' + paragraph("外链可见文字") + '</w:hyperlink>'
        body += '<w:txbxContent>' + paragraph("文本框完整内容") + '</w:txbxContent>'
        body += '<w:p><w:r><w:drawing><a:blip r:embed="image1"/></w:drawing></w:r></w:p>'
        body += paragraph('<script>alert("SECRET")</script>')
        parts = {"word/document.xml": '<w:document ' + namespace +
                 ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
                 ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><w:body>' + body + '</w:body></w:document>',
                 "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="image1" Target="media/image.png"/><Relationship Id="external" TargetMode="External" Target="https://secret.invalid"/></Relationships>',
                 "word/media/image.png": b"\x89PNG\r\n\x1a\nsynthetic-inert-image"}
        for part, value in (("header1", "页眉全部文字"), ("footer1", "页脚全部文字"),
                            ("footnotes", "脚注完整文字"), ("endnotes", "尾注完整文字")):
            parts["word/" + part + ".xml"] = '<w:root ' + namespace + '>' + paragraph(value) + '</w:root>'
        raw = package(parts)
        with self.provider(raw, "全文.docx"):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        rendered = response.content.decode()
        self.assertEqual(rendered.count("正文完整序号"), 160)
        for marker in ("正文完整序号159尾文", "表格最终单元格", "外链可见文字", "文本框完整内容",
                       "页眉全部文字", "页脚全部文字", "脚注完整文字", "尾注完整文字", "data:image/png;base64,"):
            self.assertIn(marker, rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("https://secret.invalid", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_docx_embedded_object_reads_only_emf_display_cache_and_rejects_missing_or_linked_cache(self):
        from PIL import Image
        if not hasattr(Image.core, "drawwmf"):
            self.skipTest("Passive EMF display requires the installed Windows GDI handler")
        # Synthetic rectangle, no business document/image fixture or application.
        emf = struct.pack('<6I4i4I2H3I4i', 1, 88, 0, 0, 100, 100, 0, 0, 2646, 2646,
                          0x464d4520, 0x10000, 132, 3, 1, 0, 0, 0, 0, 100, 100, 26, 26)
        emf += struct.pack('<2I4i', 43, 24, 10, 10, 90, 90) + struct.pack('<5I', 14, 20, 0, 0, 20)
        object_markup = ('<w:object><v:shape id="cached"><v:imagedata r:id="image"/></v:shape>'
                         '<o:OLEObject Type="Embed" ShapeID="cached" r:id="object"/></w:object>')
        def original(markup=object_markup, external="", image=emf):
            return package({
                "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
                '<w:body><w:p><w:r><w:t>完整首段</w:t>' + markup + '<w:t>完整尾段</w:t></w:r></w:p></w:body></w:document>',
                "word/_rels/document.xml.rels": '<Relationships><Relationship Id="image" Target="media/cache.emf" ' + external +
                '/><Relationship Id="object" Target="embeddings/object.bin"/></Relationships>',
                "word/media/cache.emf": image,
                "word/embeddings/object.bin": b"deliberately-not-a-valid-executable-object"})
        raw = original()
        with self.provider(raw, "知识库/缓存图.docx"), patch.object(service, "list_chunks", side_effect=AssertionError("chunks")):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        rendered = response.content.decode()
        self.assertIn("完整首段", rendered)
        self.assertIn("完整尾段", rendered)
        self.assertEqual(rendered.count("data:image/png;base64,"), 1)
        self.assertNotIn("object.bin", rendered)
        self.assertNotIn("OLEObject", rendered)
        with self.provider(raw, "知识库/缓存图.docx"):
            self.assertEqual(self.request(api.document_download).content, raw)
        for unsafe in (original(object_markup.replace('<v:imagedata r:id="image"/>', '')),
                       original(object_markup.replace('Type="Embed"', 'Type="Link"')),
                       original(external='TargetMode="External"'), original(image=b"not-a-renderable-cache")):
            with self.subTest(unsafe=unsafe[:20]), self.provider(unsafe, "对象.docx"):
                self.assertEqual(self.request().status_code, 415)
        excessive = bytearray(emf)
        struct.pack_into('<4i', excessive, 24, 0, 0, 2646000, 2646000)  # Large physical frame, excessive 96 dpi raster.
        with self.provider(original(image=bytes(excessive)), "大图.docx"):
            self.assertEqual(self.request().status_code, 413)
        from PIL import WmfImagePlugin
        load = WmfImagePlugin.WmfStubImageFile.load
        def load_and_revoke(image, *args, **kwargs):
            self.grants[str(self.user.pk)] = {"dataset-05": ["other"]}
            return load(image, *args, **kwargs)
        with self.provider(raw, "知识库/缓存图.docx"), patch.object(WmfImagePlugin.WmfStubImageFile, "load", load_and_revoke):
            revoked = self.request()
        self.assertEqual(revoked.status_code, 403)
        self.assertNotIn(b"data:image", revoked.content)

    def test_forbidden_invalid_and_changed_grants_or_config_release_no_file(self):
        with patch.object(service, "_open") as provider:
            self.assertEqual(self.request(document_id="hidden").status_code, 404)
            self.assertEqual(self.request(query="?url=https://secret.invalid").status_code, 400)
            provider.assert_not_called()
        raw = pdf("PRIVATE FILE SECRET")
        def revoke():
            self.grants[str(self.user.pk)] = {"dataset-05": ["other"]}
        with self.provider(raw, "原件.pdf", on_read=revoke):
            response = self.request()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"PRIVATE FILE SECRET", response.content)
        self.grants[str(self.user.pk)] = {"dataset-05": ["doc-a"]}
        self.configuration.side_effect = [CONFIG, CONFIG, CONFIG, (URL, "changed-token", CONFIG[2])]
        with self.provider(raw, "原件.pdf"):
            response = self.request()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"PRIVATE FILE SECRET", response.content)

    def test_size_truncation_redirect_and_unsupported_formats_fail_explicitly(self):
        large = wire_documents([document("doc-a", "large.pdf", size=FILE_LIMIT + 1)])
        with patch.object(service, "_open", return_value=ProviderResponse(large)) as provider:
            response = self.request()
        self.assertEqual(response.status_code, 413)
        self.assertEqual(provider.call_count, 1)
        raw = pdf("tail")
        for received in (raw[:-1], raw + b"EXTRA"):
            reply = OriginalResponse(received)
            reply.headers = {}  # Even without Content-Length, metadata checks EOF.
            with patch.object(service, "_open", side_effect=[ProviderResponse(wire_documents([
                    document("doc-a", "原文.pdf", size=len(raw))])), reply]):
                self.assertEqual(self.request().status_code, 502)
        redirect = HTTPError(URL, 302, "redirect", {}, BytesIO())
        with patch.object(service, "_open", side_effect=[ProviderResponse(wire_documents([
                document("doc-a", "原文.pdf", size=len(raw))])), redirect]):
            self.assertEqual(self.request().status_code, 503)
        vector = package({"word/document.xml":
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:body><w:p><w:r><w:drawing><a:blip r:embed="svg"/></w:drawing></w:r></w:p></w:body></w:document>',
            "word/_rels/document.xml.rels": '<Relationships><Relationship Id="svg" Target="media/graphic.svg"/></Relationships>',
            "word/media/graphic.svg": "<svg/>"})
        strict = package({"word/document.xml": '<document xmlns="http://purl.oclc.org/ooxml/wordprocessingml/main"><body><p><r><t>NEVER DROP</t></r></p></body></document>'})
        for content, name in ((b"legacy", "old.doc"), (docx(extras={"word/charts/chart1.xml": "<chart/>"}), "chart.docx"),
                              (vector, "vector.docx"), (strict, "strict.docx")):
            with self.subTest(name=name), self.provider(content, name):
                self.assertEqual(self.request().status_code, 415)

    def test_html_passive_full_reading_retains_tail_tables_and_rejects_missing_embedded_content(self):
        image = "iVBORw0KGgpzeW50aGV0aWM="
        raw = ("<html><head><link rel='stylesheet' href='https://secret.invalid/css'>"
               "<script src='https://secret.invalid/script'>EVIL SCRIPT</script></head>"
               "<body onload='alert(1)'><h1>首段标题</h1>" + "<p>完整正文</p>" * 300 +
               "<ol start='3'><li>完整列表</li></ol><table><tr><th>表头</th>"
               "<td colspan='2'>最终表格单元格</td></tr></table>"
               "<a href='javascript:alert(1)' onclick='alert(1)'>超链接正文</a>"
               "<img src='data:image/png;base64," + image + "' onerror='alert(1)'>"
               "<script>EVIL SECRET</script>脚本之后正文<strong>尾段标记</strong></body></html>").encode()
        with self.provider(raw, "source.html"):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        rendered = response.content.decode()
        self.assertEqual(rendered.count("完整正文"), 300)
        for marker in ("首段标题", "尾段标记", "完整列表", "最终表格单元格", "表头", "超链接正文", "脚本之后正文",
                       "<table>", '<td colspan="2">', '<ol start="3">', "data:image/png;base64," + image):
            self.assertIn(marker, rendered)
        for unsafe in ("<script", "onclick", "onload", "onerror", "javascript:", "secret.invalid", "EVIL"):
            self.assertNotIn(unsafe, rendered)
        self.assertTrue(response["Content-Security-Policy"].startswith("sandbox;"))
        legacy = ("<html><head><script>EVIL HEAD</script></head><body><h1>首段错配标题</p>"
                  "<p class='first' class='duplicate'>未闭合正文 & 未知实体&business"
                  "<table><tr><td colspan='2'>表格末格</th></tr></table>"
                  "<img src='https://secret.invalid/logo.png' alt='图片描述' onclick='alert(1)'>"
                  "<div style='background:url(https://secret.invalid/bg.png)'>背景正文</div>"
                  "<button onclick='alert(1)'>按钮可见文字</button>"
                  "<script>EVIL BODY</script>尾段错配标记</body></html>").encode()
        with self.provider(legacy, "legacy.html"):
            readable = self.request()
        self.assertEqual(readable.status_code, 200)
        legacy_view = readable.content.decode()
        for marker in ("首段错配标题", "未闭合正文", "&amp;business", "<table>", "表格末格", "背景正文", "按钮可见文字", "尾段错配标记",
                       "全文文字阅读，外部图片未加载", "外部图片未加载，请下载原文件查看：图片描述"):
            self.assertIn(marker, legacy_view)
        self.assertEqual(legacy_view.count('class="image-placeholder"'), 1)
        for unsafe in ("secret.invalid", "onclick", "EVIL", "<script"):
            self.assertNotIn(unsafe, legacy_view)
        for embedded in ("<iframe src='https://secret.invalid/'>正文</iframe>",
                         "<svg><text>矢量正文</text></svg>", "<img src='data:image/svg+xml;base64,PHN2Zy8+'>",
                         "<canvas>图形缺失</canvas>"):
            with self.subTest(embedded=embedded), self.provider(("<body>开始" + embedded + "结束</body>").encode(), "unsafe.html"):
                rejected = self.request()
                self.assertEqual(rejected.status_code, 415)
                self.assertEqual(rejected.data["code"], "unsupported_preview")
        markdown = "# Markdown标题\n\n完整正文\n尾段标记".encode()
        with self.provider(markdown, "source.md"):
            text = self.request()
        self.assertEqual(text["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(text.content, markdown)
        with self.provider(b"PKbroken", "broken.docx"):
            self.assertEqual(self.request().status_code, 502)
