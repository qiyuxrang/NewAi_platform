"""Render audited private DOCX/PPTX snapshots in an owned Linux session.

System Python supplies UNO; document Python audits OOXML and rasterizes PDFs.
Conversion never grants visual or business approval.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid


class RenderCancelled(Exception):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cancel(signum, frame):
    raise RenderCancelled("Render cancelled")


def uno_worker(pipe, source, output, kind="word"):
    import uno

    def properties(**values):
        result = []
        for name, value in values.items():
            item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
            item.Name, item.Value = name, value
            result.append(item)
        return tuple(result)

    context = uno.getComponentContext()
    resolver = context.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", context)
    deadline = time.monotonic() + 30
    while True:
        try:
            remote = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("LibreOffice listener did not become ready") from None
            time.sleep(0.1)
    desktop = remote.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remote)
    document = desktop.loadComponentFromURL(
        Path(source).resolve().as_uri(), "_blank", 0,
        properties(Hidden=True, ReadOnly=True, PickListEntry=False, StartPresentation=False,
                   MacroExecutionMode=uno.getConstantByName("com.sun.star.document.MacroExecMode.NEVER_EXECUTE"),
                   UpdateDocMode=uno.getConstantByName("com.sun.star.document.UpdateDocMode.NO_UPDATE")),
    )
    if document is None:
        raise RuntimeError("Renderer did not load the document")
    try:
        if kind == "word":
            if not document.supportsService("com.sun.star.text.TextDocument"):
                raise RuntimeError("Renderer did not load a Writer document")
            document.TextFields.refresh()
            indexes = document.DocumentIndexes
            toc_count = 0
            for index in range(indexes.Count):
                entry = indexes.getByIndex(index)
                entry.update()
                if entry.supportsService("com.sun.star.text.ContentIndex"):
                    cached = entry.getAnchor().getString().strip()
                    if not cached or any(marker in cached for marker in
                                         ("Error!", "错误！", "未找到目录", "No table of contents entries found")):
                        raise RuntimeError("Table of contents contains an empty or unresolved result")
                    toc_count += 1
            document.storeAsURL((Path(output) / "reviewed.docx").as_uri(),
                                properties(FilterName="Office Open XML Text", Overwrite=False))
            document.storeToURL((Path(output) / "document.pdf").as_uri(),
                                properties(FilterName="writer_pdf_Export", Overwrite=False))
            details = {"toc_count": toc_count, "toc_cached": True}
        else:
            if not document.supportsService("com.sun.star.presentation.PresentationDocument"):
                raise RuntimeError("Renderer did not load an Impress document")
            document.storeToURL((Path(output) / "slides.pdf").as_uri(),
                                properties(FilterName="impress_pdf_Export", Overwrite=False))
            details = {"slide_count": document.DrawPages.Count}
        (Path(output) / "uno.json").write_text(json.dumps(details), encoding="utf-8")
    finally:
        document.close(True)


def _group_members(group):
    members = {}
    session = os.getsid(0)
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            fields = (directory / "stat").read_bytes().decode("utf-8", errors="replace").rsplit(")", 1)[1].split()
            if int(fields[2]) == group and int(fields[3]) == session:
                members[int(directory.name)] = fields[19]
        except (OSError, ValueError, IndexError):
            continue
    return members


def _signal_group(group, sig):
    for pid, started in _group_members(group).items():
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid)
            if _group_members(group).get(pid) == started:
                signal.pidfd_send_signal(descriptor, sig)
        except ProcessLookupError:
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)


def terminate_owned(process):
    """Clean the private group even when its launcher already exited.

    Children use distinct groups inside the supervisor's session. Pidfds and
    kernel start times prevent reused process IDs from becoming cleanup targets.
    """
    if process.pid == os.getpgrp():
        raise RuntimeError("Refusing to signal the caller's process group")
    _signal_group(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(process.pid, signal.SIGKILL)
    process.wait(timeout=2)


def _check_deadline(started, timeout):
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("Renderer timed out")
    return remaining


def _new_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("Renderer produced a missing or unsafe output")
    return path


def _audit_embedded_svg(package, xml):
    # OOXML relationship auditing does not cover links inside SVG media.
    # Allow local SVG definitions; refuse scripts and resources outside the SVG.
    for name, payload in package.items():
        if not name.lower().endswith(".svg"):
            continue
        for element in xml(payload).iter():
            if element.tag.rsplit("}", 1)[-1].lower() in {"script", "foreignobject"}:
                raise ValueError("Active SVG content is forbidden")
            for attribute, value in element.attrib.items():
                local = attribute.rsplit("}", 1)[-1].lower()
                if local.startswith("on") or (local in {"href", "src"} and not value.startswith("#")):
                    raise ValueError("External SVG content is forbidden")
            styles = [*element.attrib.values(), element.text or ""]
            for style in styles:
                if re.search(r"@import", style, re.I) or any(
                        not value.strip().strip("\"'").startswith("#")
                        for value in re.findall(r"url\s*\(([^)]*)\)", style, re.I)):
                    raise ValueError("External SVG style resources are forbidden")


def render(source, output, *, executable, uno_python, timeout, kind="word"):
    if not sys.platform.startswith("linux"):
        raise RuntimeError("LibreOffice renderer requires a Linux worker")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("LibreOffice requires Linux pidfd process isolation")
    if kind not in {"word", "powerpoint"} or not 10 <= timeout <= 1200:
        raise ValueError("Invalid renderer kind or timeout")
    source, output = Path(source).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("OUTPUT_EXISTS: use a new render directory")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = output.resolve()
    scripts = Path(__file__).parent / "bj_docs" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from ooxml import audit_package, field_instructions, load_package, xml

    started = time.monotonic()
    original_hash = sha(source)
    report = {"rendered": False, "structural_pass": False, "visually_reviewed": False,
              "renderer": "LibreOffice UNO", "input_sha256": original_hash}
    listener = worker = None
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        for sig in handlers:
            signal.signal(sig, _cancel)
        with tempfile.TemporaryDirectory(prefix="portal-lo-", dir=output.parent) as temporary:
            temporary = Path(temporary).resolve()
            source_copy = temporary / ("input.docx" if kind == "word" else "input.pptx")
            source_copy.write_bytes(source.read_bytes())
            if sha(source_copy) != original_hash:
                raise RuntimeError("Source document changed before rendering")
            package = load_package(source_copy)
            audit_package(package, "word" if kind == "word" else "presentation")
            _audit_embedded_svg(package, xml)
            expected_toc = (sum(code.split()[0].upper() == "TOC" for code in
                                field_instructions(xml(package["word/document.xml"])) if code.split())
                            if kind == "word" else 0)
            if kind == "word" and expected_toc < 1:
                raise RuntimeError("Required table of contents is missing")
            profile = temporary / "profile"
            profile.mkdir(mode=0o700)
            pipe = "portal_" + uuid.uuid4().hex
            with (output / "libreoffice.log").open("wb") as log:
                try:
                    _check_deadline(started, timeout)
                    listener = subprocess.Popen(
                        [str(executable), "-env:UserInstallation=" + profile.as_uri(),
                         "--headless", "--nologo", "--nodefault", "--norestore", "--nofirststartwizard",
                         "--accept=pipe,name=" + pipe + ";urp;StarOffice.ServiceManager"],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, process_group=0,
                    )
                    worker = subprocess.Popen(
                        [str(uno_python), "-I", "-B", str(Path(__file__).resolve()), "--uno-worker",
                         pipe, str(source_copy), str(output), kind],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, process_group=0,
                    )
                    code = worker.wait(timeout=_check_deadline(started, timeout))
                    if code != 0:
                        raise RuntimeError("LibreOffice document conversion failed; see private renderer log")
                finally:
                    for sig in handlers:
                        signal.signal(sig, signal.SIG_IGN)
                    try:
                        if worker is not None:
                            terminate_owned(worker)
                    finally:
                        if listener is not None:
                            terminate_owned(listener)
                    worker = listener = None
                    for sig in handlers:
                        signal.signal(sig, _cancel)
            details = json.loads(_new_file(output / "uno.json").read_text(encoding="utf-8"))
            if not isinstance(details, dict):
                raise RuntimeError("Invalid UNO output report")
            reviewed = output / "reviewed.docx"
            if kind == "word":
                reviewed_package = load_package(_new_file(reviewed))
                audit_package(reviewed_package)
                _audit_embedded_svg(reviewed_package, xml)
                actual_toc = sum(code.split()[0].upper() == "TOC" for code in
                                 field_instructions(xml(reviewed_package["word/document.xml"])) if code.split())
                if (type(details.get("toc_count")) is not int or details["toc_count"] != expected_toc
                        or actual_toc != expected_toc or details.get("toc_cached") is not True):
                    raise RuntimeError("Required table of contents was not refreshed")
            pdf_path = _new_file(output / ("document.pdf" if kind == "word" else "slides.pdf"))
            import fitz

            with fitz.open(pdf_path) as pdf:
                if not len(pdf) or pdf.needs_pass:
                    raise RuntimeError("Rendered PDF contains no readable pages")
                if kind == "powerpoint" and (type(details.get("slide_count")) is not int
                                             or details["slide_count"] != len(pdf)):
                    raise RuntimeError("Rendered PDF does not cover every slide")
                images = []
                for index, page in enumerate(pdf):
                    _check_deadline(started, timeout)
                    destination = output / f"page-{index + 1:03}.png"
                    page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(destination)
                    images.append(str(destination))
                page_count = len(pdf)
            _check_deadline(started, timeout)
            report.update(rendered=True, structural_pass=True, **details,
                          page_count=page_count, pdf=str(pdf_path), images=images,
                          pdf_sha256=sha(pdf_path), image_sha256=[sha(path) for path in images],
                          unverified_items=["Visual page review pending", "Business facts require human approval"])
            if kind == "word":
                report.update(rendered_docx=str(reviewed), rendered_docx_sha256=sha(reviewed))
    except (Exception, KeyboardInterrupt) as error:
        report.update(rendered=False, structural_pass=False,
                      unverified_items=["Renderer timed out" if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
                                        else type(error).__name__ + ": " + str(error)])
    finally:
        for sig in handlers:
            signal.signal(sig, signal.SIG_IGN)
        try:
            if worker is not None:
                terminate_owned(worker)
        finally:
            try:
                if listener is not None:
                    terminate_owned(listener)
            finally:
                try:
                    if not source.is_file() or sha(source) != original_hash:
                        report.update(rendered=False, structural_pass=False,
                                      unverified_items=["Source document changed during rendering"])
                    (output / "render.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
                finally:
                    for sig, handler in handlers.items():
                        signal.signal(sig, handler)
    return report


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--uno-worker":
        uno_worker(*sys.argv[2:])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["word", "powerpoint"])
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--uno-python", required=True)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 1200:
        parser.error("timeout must be between 10 and 1200 seconds")
    result = render(args.source, args.output, executable=args.executable,
                    uno_python=args.uno_python, timeout=args.timeout, kind=args.kind)
    print(json.dumps(result, ensure_ascii=False))
    if not result["rendered"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
