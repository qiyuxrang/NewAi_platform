"""Audit retained real PDFs and assemble page contact sheets for human visual review."""
import json
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

run = Path(sys.argv[1]).resolve()
root = run / "retained"
output = run / "page-audit" / "published"
output.mkdir(parents=True, exist_ok=True)
records = []
evidence = run / "evidence.json"
pdf_paths = ([root / artifact["preview"]["pdf"]["path"] for artifact in json.loads(evidence.read_text(encoding="utf-8"))["artifacts"]]
             if evidence.is_file() else sorted(root.rglob("*.pdf")))
for index, pdf_path in enumerate(pdf_paths, 1):
    pages = []
    with fitz.open(pdf_path) as pdf:
        for number, page in enumerate(pdf, 1):
            text = page.get_text()
            assert text.strip(), f"empty text page: {pdf_path.name}:{number}"
            assert "\ufffd" not in text, f"replacement character: {pdf_path.name}:{number}"
            overflow = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        x0, y0, x1, y1 = span["bbox"]
                        if span["text"].strip() and (x0 < -2 or y0 < -2 or x1 > page.rect.width + 2 or y1 > page.rect.height + 2):
                            overflow.append(span["bbox"])
            assert not overflow, f"text outside page: {pdf_path.name}:{number}"
            pages.append({"page": number, "characters": len(text), "text_outside_page": len(overflow)})
        count = len(pdf)
    images = sorted(pdf_path.parent.glob("page-*.png"))
    assert len(images) == count
    sheets = []
    for offset in range(0, count, 8):
        sheet = Image.new("RGB", (1000, 1480), "#d9dde4")
        draw = ImageDraw.Draw(sheet)
        for position, source in enumerate(images[offset:offset+8]):
            with Image.open(source) as page_image:
                page_image.thumbnail((480, 338))
                x = (position % 2) * 500 + 10
                y = (position // 2) * 370 + 25
                sheet.paste(page_image.convert("RGB"), (x, y))
                draw.text((x, y-18), f"PDF {index} / Page {offset+position+1}", fill="black")
        destination = output / f"document-{index}-pages-{offset+1}-{min(offset+8,count)}.png"
        sheet.save(destination)
        sheets.append(str(destination))
    records.append({"pdf": str(pdf_path), "page_count": count, "pages": pages,
                    "contact_sheets": sheets, "visual_review": "not_run"})
(output / "audit.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(records, ensure_ascii=False, indent=2))
