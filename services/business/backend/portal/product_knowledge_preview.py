"""Complete, passive previews of the original file, never retrieval chunks."""
import base64
import json
from html import escape
from html.parser import HTMLParser
from io import BytesIO
import posixpath
import re
from math import ceil, isfinite
from time import monotonic
from zipfile import BadZipFile

from .product_service import ProductError


FILE_LIMIT = 20 * 1024 * 1024
PACKAGE_LIMIT = 32 * 1024 * 1024
HTML_LIMIT = 64 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def unsupported():
    raise ProductError("unsupported_preview", "此原文件格式暂不支持完整在线预览，请下载原文件查阅。", 415)


def too_large():
    raise ProductError("document_too_large", "原文件超过安全预览或下载上限（20 MB），请联系管理员。", 413)


def raster_mime(image):
    return ("image/png" if image.startswith(b"\x89PNG\r\n\x1a\n") else
            "image/jpeg" if image.startswith(b"\xff\xd8\xff") else
            "image/gif" if image.startswith((b"GIF87a", b"GIF89a")) else
            "image/webp" if image[:4] == b"RIFF" and image[8:12] == b"WEBP" else None)


def pdf_preview(raw, *, start_page=None, page_size=3):
    import fitz
    def limit():
        raise ProductError("preview_limit", "PDF 当前批次超过像素、体积或处理时间上限，请下载原文件查阅。", 413)
    deadline, size = monotonic() + 25, 0
    try:
        with fitz.open(stream=raw, filetype="pdf") as document:
            if document.needs_pass:
                unsupported()
            count = len(document)
            if not 1 <= count <= 10000:
                limit()
            if start_page is not None and (type(start_page) is not int or not 1 <= start_page <= count
                                          or type(page_size) is not int or not 1 <= page_size <= 5):
                raise ProductError("invalid_request", "PDF 页码或批次大小无效。", 400)
            first = 0 if start_page is None else start_page - 1
            end = count if start_page is None else min(count, first + page_size)
            pages = []
            for index in range(first, end):
                if monotonic() >= deadline:
                    limit()
                page = document[index]
                width, height = page.rect.width, page.rect.height
                if not isfinite(width) or not isfinite(height) or width <= 0 or height <= 0:
                    limit()
                item = {"page": index + 1, "width": width, "height": height}
                if start_page is not None:
                    if ceil(width * 4 / 3) * ceil(height * 4 / 3) > 8_000_000:
                        limit()
                    # ponytail: native page render has no mid-call deadline;
                    # isolate it in a process if hard interruption is required.
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(4 / 3, 4 / 3), alpha=False, colorspace=fitz.csRGB)
                    encoded = base64.b64encode(pixmap.tobytes("jpeg", jpg_quality=85)).decode("ascii")
                    item["image"] = "data:image/jpeg;base64," + encoded
                size += len(json.dumps(item, separators=(",", ":")).encode())
                if size + 1024 > HTML_LIMIT:
                    limit()
                if monotonic() >= deadline:
                    limit()
                pages.append(item)
            result = {"kind": "pdf" if start_page is None else "pdf_pages", "page_count": count, "pages": pages}
            if start_page is not None:
                result["next_page"] = end + 1 if end < count else None
            return result
    except (ValueError, RuntimeError):
        raise ProductError("invalid_response", "原 PDF 文件损坏或无法完整渲染，请下载原文件查阅。", 502) from None


def docx_html(raw, name):
    # Reuse the existing audited OOXML reader; it rejects duplicate/traversal,
    # encrypted entries, entity expansion and excessive decompression.
    from .product_assets.bj_docs.scripts.ooxml import load_package, xml
    deadline = monotonic() + 25

    def check_time():
        if monotonic() >= deadline:
            raise ProductError("preview_limit", "Word 原文件超过处理时间或单图像素上限，请下载原文件查阅。", 413)

    def passive_image(image):
        mime = raster_mime(image)
        if mime is not None:
            return mime, image
        # Word stores a passive display cache for some embedded objects. Render
        # only that EMF cache through the installed Windows GDI handler; never
        # open the embedded application, object binary, or an external resource.
        if not (image.startswith(b"\x01\x00\x00\x00") and image[40:44] == b" EMF"):
            unsupported()
        from PIL import Image
        if not hasattr(Image.core, "drawwmf"):
            unsupported()
        check_time()
        with Image.open(BytesIO(image)) as source:
            dpi = source.info.get("dpi")
            xdpi, ydpi = dpi if isinstance(dpi, tuple) else (dpi, dpi)
            if (not isinstance(xdpi, (int, float)) or not isinstance(ydpi, (int, float))
                    or not isfinite(xdpi) or not isfinite(ydpi) or min(xdpi, ydpi) <= 0
                    or ceil(source.width * 96 / xdpi) * ceil(source.height * 96 / ydpi) > 8_000_000):
                raise ProductError("preview_limit", "Word 内嵌图片超过单图像素上限，请下载原文件查阅。", 413)
            source.load(dpi=96)
            check_time()
            if source.width * source.height > 8_000_000:
                raise ProductError("preview_limit", "Word 内嵌图片超过单图像素上限，请下载原文件查阅。", 413)
            converted = BytesIO()
            source.save(converted, format="PNG")
        check_time()
        return "image/png", converted.getvalue()

    try:
        package = load_package(BytesIO(raw), max_entries=2000, max_uncompressed=PACKAGE_LIMIT)
        if "word/document.xml" not in package:
            unsupported()
        if any(path.startswith("word/charts/")
               or "vbaProject" in path for path in package):
            unsupported()
        parts = ["word/document.xml"] + sorted(path for path in package if re.fullmatch(
            r"word/(header\d+|footer\d+|footnotes|endnotes)\.xml", path))
        output = ["<!doctype html><html><head><meta charset='utf-8'><title>", escape(name),
                  "</title><style>body{font:16px/1.8 sans-serif;margin:24px;color:#222}"
                  ".paragraph{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 10px}"
                  "table{border-collapse:collapse;max-width:100%;margin:16px 0}"
                  "td{border:1px solid #ccc;padding:6px;vertical-align:top}"
                  "img{max-width:100%;height:auto}h2{font-size:18px}</style></head><body>"]
        size = sum(len(value.encode("utf-8")) for value in output)

        def emit(value):
            nonlocal size
            check_time()
            size += len(value.encode("utf-8"))
            if size > HTML_LIMIT:
                too_large()
            output.append(value)

        for part in parts:
            root = xml(package[part])
            if (not isinstance(root.tag, str) or not root.tag.startswith(W)
                    or part == "word/document.xml" and root.find(W + "body") is None):
                unsupported()
            relationship_path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            relationships = {}
            if relationship_path in package:
                for entry in xml(package[relationship_path]):
                    if entry.get("TargetMode") != "External":
                        target = posixpath.normpath(posixpath.join(posixpath.dirname(part), entry.get("Target", ""))).lstrip("/")
                        relationships[entry.get("Id")] = target

            passive_objects = set()

            def render(node):
                if not isinstance(node.tag, str):
                    return
                local = node.tag.rsplit("}", 1)[-1]
                if node.tag in {W + "del", W + "instrText", W + "moveFrom"} or local.endswith("Pr"):
                    return
                if node.tag == W + "object":
                    objects = [child for child in node.iter() if isinstance(child.tag, str)
                               and child.tag.rsplit("}", 1)[-1] == "OLEObject"]
                    shapes = [child for child in node.iter() if isinstance(child.tag, str)
                              and child.tag.rsplit("}", 1)[-1] == "shape"]
                    if not objects:
                        unsupported()
                    for embedded in objects:
                        target = relationships.get(embedded.get(R + "id"))
                        shape = next((shape for shape in shapes if shape.get("id") == embedded.get("ShapeID")), None)
                        caches = [] if shape is None else [child for child in shape.iter() if isinstance(child.tag, str)
                                                           and child.tag.rsplit("}", 1)[-1] == "imagedata"]
                        if (embedded.get("Type") != "Embed" or not target or not target.startswith("word/embeddings/")
                                or target not in package or not caches):
                            unsupported()
                        passive_objects.add(embedded)
                if local == "OLEObject" and node in passive_objects:
                    return
                if local in {"altChunk", "chart", "OLEObject", "sym"}:
                    unsupported()
                if local == "AlternateContent":
                    render(node[0])
                    return
                if node.tag == W + "t" or local == "t" and "math" in node.tag:
                    emit(escape(node.text or ""))
                    return
                if node.tag in {W + "br", W + "cr"}:
                    emit("<br>")
                    return
                if node.tag == W + "tab":
                    emit("\t")
                    return
                if node.tag in {W + "noBreakHyphen", W + "softHyphen"}:
                    emit("&#8209;" if node.tag == W + "noBreakHyphen" else "&shy;")
                    return
                if local in {"blip", "imagedata"}:
                    target = relationships.get(node.get(R + "embed") or node.get(R + "id"))
                    image = package.get(target)
                    if not image:
                        unsupported()
                    mime, image = passive_image(image)
                    emit('<img alt="文档内嵌图片" src="data:' + mime + ';base64,' +
                         base64.b64encode(image).decode("ascii") + '">')
                    return
                tags = {W + "p": ('<div class="paragraph">', "</div>"),
                        W + "tbl": ("<table>", "</table>"), W + "tr": ("<tr>", "</tr>"),
                        W + "tc": ("<td>", "</td>")}
                opening, closing = tags.get(node.tag, ("", ""))
                emit(opening)
                for child in node:
                    render(child)
                emit(closing)

            if part != "word/document.xml":
                label = "页眉" if "/header" in part else "页脚" if "/footer" in part else "脚注" if "/footnotes" in part else "尾注"
                emit("<h2>" + label + "</h2>")
            render(root)
        emit("</body></html>")
        return "".join(output).encode("utf-8")
    except (ValueError, KeyError, TypeError, IndexError, RecursionError, OSError, BadZipFile):
        raise ProductError("invalid_response", "原文件损坏或不符合安全预览要求，请联系管理员。", 502) from None


def passive_html(content, name):
    allowed = set("h1 h2 h3 h4 h5 h6 p div span table caption thead tbody tfoot tr th td ol ul li "
                  "blockquote pre code br hr b strong em i u s del ins sup sub small abbr figure figcaption "
                  "section article header footer main aside address details summary dl dt dd mark time".split())
    embedded = {"iframe", "frame", "frameset", "object", "embed", "svg", "math", "canvas",
                "video", "audio", "source", "picture", "input", "select", "textarea"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    output, stack, ignored = [], [], []
    size, missing_images = 0, 0
    def emit(value):
        nonlocal size
        size += len(value.encode("utf-8"))
        if size > HTML_LIMIT:
            too_large()
        output.append(value)

    class PassiveReader(HTMLParser):
        # Tokens preserve all body text even in malformed legacy export markup;
        # unlike a repaired DOM, no subtree is discarded to enforce tree depth.
        def handle_starttag(self, tag, attrs):
            nonlocal missing_images
            if ignored or tag in {"head", "script", "style", "template"}:
                if tag not in void:
                    ignored.append(tag)
                return
            if tag in {"html", "body", "meta", "link", "base"}:
                return
            attributes = dict(reversed(attrs))
            if tag in embedded:
                unsupported()
            safe = {}
            if tag == "img":
                sources = [value for key, value in attrs if key == "src"]
                source = sources[0] if sources else ""
                if not source or not source.lower().startswith("data:") or attributes.get("srcset") or len(set(sources)) > 1:
                    missing_images += 1
                    alt = attributes.get("alt") or ""
                    emit('<p class="image-placeholder">外部图片未加载，请下载原文件查看' +
                         ("：" + escape(alt) if alt else "") + "</p>")
                    return
                match = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=]+)", source, re.I)
                if match is None:
                    unsupported()
                try:
                    image = base64.b64decode(match[2], validate=True)
                except ValueError:
                    unsupported()
                if raster_mime(image) != match[1].lower():
                    unsupported()
                safe = {"src": "data:" + match[1].lower() + ";base64," + match[2],
                        "alt": attributes.get("alt") or "文档内嵌图片"}
                rendered_tag = "img"
            else:
                rendered_tag = tag if tag in allowed else "span"
                for key in ("colspan", "rowspan") if tag in {"td", "th"} else ("start", "value") if tag in {"ol", "li"} else ():
                    value = attributes.get(key)
                    if value is not None and re.fullmatch(r"-?\d{1,6}", value):
                        safe[key] = value
                if "hidden" in attributes:
                    safe["hidden"] = "hidden"
            emit("<" + rendered_tag + "".join(' ' + key + '="' + escape(value, quote=True) + '"' for key, value in safe.items()) + ">")
            if tag not in void:
                stack.append((tag, rendered_tag))

        def handle_endtag(self, tag):
            if ignored:
                if tag in ignored:
                    del ignored[len(ignored) - 1 - ignored[::-1].index(tag):]
                return
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0] == tag:
                    while len(stack) > index:
                        emit("</" + stack.pop()[1] + ">")
                    break

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_data(self, value):
            if not ignored:
                emit(escape(value))

    emit("<!doctype html><html><head><meta charset='utf-8'><title>" + escape(name) +
         "</title><style>body{font:16px/1.8 sans-serif;margin:24px;color:#222;overflow-wrap:anywhere}"
         "table{border-collapse:collapse;max-width:100%;margin:16px 0}"
         "td,th{border:1px solid #ccc;padding:6px;vertical-align:top}"
         "img{max-width:100%;height:auto}pre{white-space:pre-wrap}</style></head><body>")
    parser = PassiveReader(convert_charrefs=True)
    parser.feed(content)
    parser.close()
    while stack:
        emit("</" + stack.pop()[1] + ">")
    emit("</body></html>")
    emit('<p class="reading-notice">' + ("全文文字阅读，外部图片未加载；原始排版与图片请下载原文件查看。" if missing_images else
                                         "全文文字阅读；原始排版与图片请下载原文件查看。") + "</p>")
    output.insert(1, output.pop())
    return "".join(output).encode("utf-8")


def preview(raw, name):
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == "pdf":
        if not raw.startswith(b"%PDF-"):
            raise ProductError("invalid_response", "原文件不是有效 PDF。", 502)
        return json.dumps(pdf_preview(raw), separators=(",", ":")).encode(), "application/json"
    if suffix == "docx":
        return docx_html(raw, name), "text/html; charset=utf-8"
    if suffix in {"txt", "md", "csv", "json", "html", "htm", "xml", "log"}:
        # Strict decoding never drops characters; Markdown stays full source text.
        for encoding in ("utf-8-sig", "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "gb18030"):
            try:
                content = raw.decode(encoding)
                if "\0" in content:
                    break
                if suffix in {"html", "htm"}:
                    return passive_html(content, name), "text/html; charset=utf-8"
                return content.encode("utf-8"), "text/plain; charset=utf-8"
            except UnicodeError:
                pass
    unsupported()
