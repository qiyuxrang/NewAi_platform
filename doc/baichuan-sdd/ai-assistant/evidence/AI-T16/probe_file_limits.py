"""Bounded synthetic parser measurements. No database, model or search calls.

Run from any directory with the existing company-test Python interpreter.
Fixtures and parser staging live only in a temporary ignored .runtime directory.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import zipfile

REPO = Path(__file__).resolve().parents[5]
BACKEND = REPO / "services/business/backend"
OCR_PYTHON = REPO / ".runtime/company-test/cloud-ocr/Scripts/python.exe"


def configure(directory):
    allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "PATHEXT", "COMSPEC",
               "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES",
               "PROGRAMFILES(X86)", "SYSTEMDRIVE", "PROCESSOR_ARCHITECTURE"}
    clean = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    os.environ.clear()
    os.environ.update(clean)
    os.environ.update(PORTAL_SECRET_KEY="baichuan-synthetic-file-capacity-20261017-only",
                      PORTAL_DEBUG="1", PORTAL_HTTPS="0", DJANGO_SETTINGS_MODULE="config.settings",
                      PORTAL_SQLITE_PATH=str(directory / "unused-isolated.sqlite3"))
    sys.path[:0] = [str(BACKEND), str(BACKEND.parent)]
    import django
    django.setup()
    from django.conf import settings
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert Path(settings.DATABASES["default"]["NAME"]) == directory / "unused-isolated.sqlite3"
    # Also fail closed against an accidental outbound call from this probe.
    def deny_network(*args, **kwargs):
        raise AssertionError("This capacity probe forbids network access")
    socket.socket = socket.create_connection = socket.getaddrinfo = deny_network


def docx(paragraphs):
    from xml.sax.saxutils import escape
    output = io.BytesIO()
    # Stored entries ensure character-limit fixtures do not trip archive-ratio guards.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        body = "".join(f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>" for text in paragraphs)
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
    return output.getvalue()


def native_pdf(pages):
    import fitz
    document = fitz.open()
    for number in range(1, pages + 1):
        document.new_page().insert_text((40, 60), f"SYNTHETIC CAPACITY PAGE {number}")
    content = document.tobytes()
    document.close()
    return content


def scanned_pdf():
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    document = fitz.open()
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 36)
    for number in range(1, 14):
        image = Image.new("RGB", (1000, 260), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 45), "虚构容量测试：ITSS 二级", font=font, fill="black")
        draw.text((35, 115), f"PAGE {number:02d}" if number < 13 else "OMITTED_PAGE13_SENTINEL", font=font, fill="black")
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        document.new_page(width=500, height=130).insert_image(fitz.Rect(0, 0, 500, 130), stream=stream.getvalue())
        image.close()
    content = document.tobytes()
    document.close()
    return content


def measure(case, filename, content, **settings_overrides):
    from django.test import override_settings
    from portal.product_intake import run_parser
    from portal.product_storage import StorageError
    start = time.monotonic()
    row = {"case": case, "input_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    with override_settings(**settings_overrides):
        try:
            parsed = run_parser(filename, content)
        except StorageError as error:
            row.update(error_code=error.code, error_detail=error.detail)
            parsed = None
        else:
            blocks = parsed["blocks"]
            row.update(status=parsed["status"], method=parsed["method"], characters=parsed["character_count"],
                       block_count=len(blocks), truncated=parsed["truncated"], warnings=parsed["warnings"],
                       first_location=blocks[0]["location"] if blocks else None,
                       last_location=blocks[-1]["location"] if blocks else None,
                       pages=sorted({b["location"]["page"] for b in blocks if "page" in b["location"]}))
    row["elapsed_seconds"] = round(time.monotonic() - start, 3)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row, parsed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    with tempfile.TemporaryDirectory(prefix="baichuan-AI-T16-files-", dir=REPO / ".runtime") as directory_name:
        directory = Path(directory_name)
        configure(directory)
        from django.test import override_settings
        from django.db import connections
        with override_settings(PRODUCT_STORAGE_ROOT=directory / "private", PRODUCT_PARSER_PYTHON=str(OCR_PYTHON),
                               PRODUCT_OCR_ENABLED=True, PRODUCT_PARSE_TIMEOUT_SECONDS=90):
            row, parsed = measure("native_pdf_100_pages", "synthetic.pdf", native_pdf(100))
            assert row["status"] == "completed" and row["pages"] == list(range(1, 101))
            rows.append(row)
            row, parsed = measure("native_pdf_101_pages_rejected", "synthetic.pdf", native_pdf(101))
            assert row["error_code"] == "page_limit" and parsed is None
            rows.append(row)
            row, parsed = measure("scan_pdf_13_pages_ocr_capped_at_12", "synthetic.pdf", scanned_pdf())
            assert row["status"] == "partial" and row["method"] == "ocr"
            assert row["pages"] == list(range(1, 13))
            assert any(w["code"] == "ocr_limit" and w["location"] == {"page": 13} for w in row["warnings"])
            assert any(w["code"] == "ocr_review_required" for w in row["warnings"])
            assert "OMITTED" not in "\n".join(b["text"] for b in parsed["blocks"])
            rows.append(row)
            exact = [f"SYNTHETIC PARAGRAPH {number:03d} ".ljust(1000, "X") for number in range(1, 201)]
            row, parsed = measure("docx_exact_200000_characters", "synthetic.docx", docx(exact))
            assert row["status"] == "completed" and row["characters"] == 200000 and row["block_count"] == 200
            assert parsed["blocks"][-1]["text"] == exact[-1]
            rows.append(row)
            row, parsed = measure("docx_200001_characters_partial", "synthetic.docx", docx(exact + ["Z"]))
            assert row["status"] == "partial" and row["characters"] == 200000 and row["truncated"]
            assert any(w["code"] == "extraction_limit" and w["location"]["paragraph"] == 201 for w in row["warnings"])
            assert len(parsed["blocks"]) == 200 and all(b["text"] != "Z" for b in parsed["blocks"])
            rows.append(row)
            row, parsed = measure("docx_single_200001_character_block_failed", "synthetic.docx", docx(["Y" * 200001]))
            assert row["status"] == "failed" and row["characters"] == 0 and row["truncated"]
            assert {w["code"] for w in row["warnings"]} == {"extraction_limit", "no_text"}
            rows.append(row)
            row, parsed = measure("docx_5001_blocks_partial", "synthetic.docx", docx([f"SYNTHETIC ROW {i:04d}" for i in range(1, 5002)]))
            assert row["status"] == "partial" and row["block_count"] == 5000 and row["truncated"]
            assert any(w["location"].get("paragraph") == 5001 for w in row["warnings"])
            rows.append(row)
            row, parsed = measure("subprocess_timeout_rejects_incomplete_result", "synthetic.docx", docx(exact),
                                  PRODUCT_PARSE_TIMEOUT_SECONDS=0.001)
            assert row["error_code"] == "parse_timeout" and parsed is None
            rows.append(row)
        assert connections["default"].connection is None, "Probe must not open any database"
        assert not (directory / "unused-isolated.sqlite3").exists()
        assert not list((directory / "private" / ".parsing").iterdir()), "Parser staging must be cleaned"
    print(json.dumps({"summary": "PASS", "cases": len(rows), "database_opened": False,
                      "network_calls": 0, "model_calls": 0, "fixtures_removed": not directory.exists()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
