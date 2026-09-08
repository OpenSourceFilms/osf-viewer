"""Semantic extraction for office/document formats.

DOCX/XLSX/PPTX/ODT/ODS/ODP are handled by pure-Python libraries
(python-docx/openpyxl/python-pptx/odfpy) -- no JVM/Tika needed. See the
"why no Tika" note in DOCS.md: this pod has no Java runtime at all, and
these libraries give equal-or-better structural fidelity (paragraph order,
headings, tables, worksheet/slide boundaries, speaker notes) for a much
smaller footprint than installing a JVM + a ~70MB Tika jar would have cost.

LibreOffice headless is used for two things only: /preview.pdf rendering
(uniform across every format here), and converting legacy binary formats
(.doc/.xls/.ppt/.rtf) to their modern XML equivalent first, so they reuse
the exact same structural extractor as native DOCX/XLSX/PPTX rather than a
separate, lower-fidelity code path.

Every public function here may raise -- callers (inspectors.get_text /
get_preview_pdf) already wrap every handler in a broad except and demote to
the generic fallback, so no internal top-level try/except is needed to keep
the "/text never 500s" contract.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import cache as _cache

DOCX_EXTS = {"docx"}
XLSX_EXTS = {"xlsx"}
PPTX_EXTS = {"pptx"}
ODT_EXTS = {"odt"}
ODS_EXTS = {"ods"}
ODP_EXTS = {"odp"}
LEGACY_OFFICE_EXTS = {"doc", "xls", "ppt", "rtf"}
OFFICE_EXTS = DOCX_EXTS | XLSX_EXTS | PPTX_EXTS | ODT_EXTS | ODS_EXTS | ODP_EXTS | LEGACY_OFFICE_EXTS

MAX_OFFICE_SRC_BYTES = 200 * 1024 * 1024   # size cap before even attempting extraction
MAX_CONVERT_SRC_BYTES = 150 * 1024 * 1024  # separate, tighter cap before invoking soffice at all
MAX_DOCX_CHARS = 2_000_000
MAX_ODF_CHARS = 2_000_000
MAX_TABLE_ROWS = 200
MAX_XLSX_ROWS_PER_SHEET = 200
MAX_XLSX_COLS = 50
MAX_XLSX_TOTAL_CELLS = 20_000
MAX_SLIDES = 300
LO_TIMEOUT_S = 45

SOFFICE_BIN = shutil.which("soffice") or "/usr/bin/soffice"

_MACRO_LOCKDOWN_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
           xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
  <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
 </item>
</oor:items>
"""

_LO_PROFILE_TEMPLATE: Optional[Path] = None


def _lo_profile_template() -> Path:
    """Seed LibreOffice profile with macro execution locked to 'never'
    (MacroSecurityLevel=3), created once and copied fresh for every
    conversion (cheap -- a couple of tiny XML files) so no two conversions
    share mutable profile state, and every one also gets its own single-
    instance lock rather than colliding with a concurrent request.
    """
    global _LO_PROFILE_TEMPLATE
    if _LO_PROFILE_TEMPLATE is not None and _LO_PROFILE_TEMPLATE.exists():
        return _LO_PROFILE_TEMPLATE
    _cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmpl = _cache.CACHE_DIR / "lo_profile_template"
    user_dir = tmpl / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "registrymodifications.xcu").write_text(_MACRO_LOCKDOWN_XCU)
    _LO_PROFILE_TEMPLATE = tmpl
    return tmpl


def _check_size(path: Optional[Path], data: Optional[bytes], cap: int) -> None:
    size = len(data) if data is not None else (path.stat().st_size if path else 0)
    if size > cap:
        raise ValueError(f"file is {size} bytes, over the {cap} byte cap for office "
                          f"extraction -- degrading to the generic fallback report")


def _convert_with_soffice(path: Optional[Path], data: Optional[bytes], src_ext: str,
                           target_ext: str, timeout: int = LO_TIMEOUT_S) -> Optional[bytes]:
    """Run one soffice --headless --convert-to conversion in full isolation:
    its own temp working dir + input/output paths under the cache root
    (never /workspace directly), its own throwaway profile copy (macro
    execution disabled), and a hard timeout. Returns None (never raises) on
    any failure -- callers treat that as "no result from this rung", not an
    error, and fall further down the degradation ladder.
    """
    try:
        _check_size(path, data, MAX_CONVERT_SRC_BYTES)
    except ValueError:
        return None
    template = _lo_profile_template()
    _cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(_cache.CACHE_DIR)) as td:
        td_path = Path(td)
        profile_dir = td_path / "profile"
        shutil.copytree(template, profile_dir)
        in_path = td_path / f"input.{src_ext}"
        if data is not None:
            in_path.write_bytes(data)
        else:
            shutil.copy(path, in_path)
        out_dir = td_path / "out"
        out_dir.mkdir()
        cmd = [
            SOFFICE_BIN, "--headless", "--invisible", "--nologo", "--nofirststartwizard",
            "--norestore", "--nolockcheck",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to", target_ext, "--outdir", str(out_dir), str(in_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0:
            return None
        out_path = out_dir / f"input.{target_ext}"
        if not out_path.is_file():
            return None
        return out_path.read_bytes()


def _legacy_txt_fallback(path: Optional[Path], data: Optional[bytes], src_ext: str) -> str:
    out = _convert_with_soffice(path, data, src_ext, "txt")
    if out is not None:
        return out.decode("utf-8", errors="replace")
    raise RuntimeError(f"LibreOffice could not convert this .{src_ext} file")


def _text_docx(path: Optional[Path], data: Optional[bytes], converted_from: Optional[str] = None) -> str:
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    src = io.BytesIO(data) if data is not None else str(path)
    doc = docx.Document(src)
    lines: list[str] = []
    if converted_from:
        lines.append(f"[converted from legacy .{converted_from} via LibreOffice headless]")
    cp = doc.core_properties
    meta = [f"{k}: {v}" for k, v in (
        ("title", cp.title), ("author", cp.author),
        ("created", cp.created), ("modified", cp.modified),
    ) if v]
    if meta:
        lines.append("--- metadata ---")
        lines.extend(meta)
        lines.append("")

    n_chars = 0
    for child in doc.element.body.iterchildren():
        if n_chars > MAX_DOCX_CHARS:
            lines.append(f"... truncated at {MAX_DOCX_CHARS} characters")
            break
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = para.text
            if not text.strip():
                continue
            style = (para.style.name or "") if para.style else ""
            low = style.lower()
            if low.startswith("heading") or low == "title":
                digits = "".join(ch for ch in style if ch.isdigit())
                line = f"{'#' * (int(digits) if digits else 1)} {text}"
            else:
                line = text
            lines.append(line)
            n_chars += len(line)
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            rows_out = []
            for r_i, row in enumerate(table.rows):
                if r_i >= MAX_TABLE_ROWS:
                    rows_out.append(f"... table truncated at {MAX_TABLE_ROWS} rows")
                    break
                cells = [c.text.replace("\n", " ").strip() for c in row.cells]
                rows_out.append(" | ".join(cells))
            table_text = "\n".join(rows_out)
            lines.append("[table]")
            lines.append(table_text)
            n_chars += len(table_text)
    return "\n".join(lines) if lines else "[no extractable text content]"


def _text_xlsx(path: Optional[Path], data: Optional[bytes], converted_from: Optional[str] = None) -> str:
    import openpyxl

    src = io.BytesIO(data) if data is not None else str(path)
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    lines: list[str] = []
    if converted_from:
        lines.append(f"[converted from legacy .{converted_from} via LibreOffice headless]")
    lines.append(f"worksheets: {len(wb.sheetnames)} -> {', '.join(wb.sheetnames)}")
    lines.append("")
    total_cells = 0
    for ws in wb.worksheets:
        # ws.dimensions isn't available on read_only worksheets (only on the
        # regular Worksheet class) -- max_row/max_column work in both modes.
        lines.append(f"--- sheet: {ws.title} (rows<={ws.max_row}, cols<={ws.max_column}) ---")
        row_count = 0
        for row in ws.iter_rows(max_row=MAX_XLSX_ROWS_PER_SHEET, max_col=MAX_XLSX_COLS, values_only=True):
            if total_cells >= MAX_XLSX_TOTAL_CELLS:
                lines.append(f"... stopped at the global {MAX_XLSX_TOTAL_CELLS}-cell cap across all sheets")
                break
            cells = ["" if v is None else str(v) for v in row]
            while cells and cells[-1] == "":
                cells.pop()  # trim trailing padding max_col introduces past real data
            if not cells:
                continue
            lines.append(" | ".join(cells))
            row_count += 1
            total_cells += len(cells)
        if row_count >= MAX_XLSX_ROWS_PER_SHEET:
            lines.append(f"... sheet truncated at {MAX_XLSX_ROWS_PER_SHEET} rows / {MAX_XLSX_COLS} cols")
        lines.append("")
        if total_cells >= MAX_XLSX_TOTAL_CELLS:
            break
    wb.close()
    return "\n".join(lines)


def _text_pptx(path: Optional[Path], data: Optional[bytes], converted_from: Optional[str] = None) -> str:
    import pptx

    src = io.BytesIO(data) if data is not None else str(path)
    prs = pptx.Presentation(src)
    lines: list[str] = []
    if converted_from:
        lines.append(f"[converted from legacy .{converted_from} via LibreOffice headless]")
    cp = prs.core_properties
    meta = [f"{k}: {v}" for k, v in (("title", cp.title), ("author", cp.author)) if v]
    if meta:
        lines.append("--- metadata ---")
        lines.extend(meta)
        lines.append("")

    for i, slide in enumerate(prs.slides, start=1):
        if i > MAX_SLIDES:
            lines.append(f"... truncated at {MAX_SLIDES} slides")
            break
        lines.append(f"--- slide {i} ---")
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text_frame.text
                if text.strip():
                    lines.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.replace("\n", " ").strip() for c in row.cells]
                    lines.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text
            if notes.strip():
                lines.append(f"[notes] {notes}")
        lines.append("")
    return "\n".join(lines) if lines else "[no extractable slide content]"


# --------------------------------------------------------------------------
# public entry points -- called from inspectors.get_text() / get_preview_pdf()
# --------------------------------------------------------------------------

def get_text(path: Optional[Path], data: Optional[bytes], filename_hint: str, kind: str) -> str:
    """May raise -- inspectors.get_text()'s wrapper demotes any exception to
    the generic binary report, so legacy-format conversion failures degrade
    cleanly rather than needing their own top-level try/except here.
    """
    _check_size(path, data, MAX_OFFICE_SRC_BYTES)
    if kind == "docx":
        return _text_docx(path, data)
    if kind == "xlsx":
        return _text_xlsx(path, data)
    if kind == "pptx":
        return _text_pptx(path, data)
    if kind == "odt":
        return _text_odt(path, data)
    if kind == "ods":
        return _text_ods(path, data)
    if kind == "odp":
        return _text_odp(path, data)
    if kind in ("doc", "rtf"):
        converted = _convert_with_soffice(path, data, kind, "docx")
        if converted is not None:
            return _text_docx(None, converted, converted_from=kind)
        return _legacy_txt_fallback(path, data, kind)
    if kind == "xls":
        converted = _convert_with_soffice(path, data, kind, "xlsx")
        if converted is not None:
            return _text_xlsx(None, converted, converted_from=kind)
        return _legacy_txt_fallback(path, data, kind)
    if kind == "ppt":
        converted = _convert_with_soffice(path, data, kind, "pptx")
        if converted is not None:
            return _text_pptx(None, converted, converted_from=kind)
        return _legacy_txt_fallback(path, data, kind)
    raise ValueError(f"unhandled office kind: {kind}")


def get_preview_pdf(path: Optional[Path], data: Optional[bytes], filename_hint: str, kind: str,
                     relpath: str, size: int, mtime: float) -> Optional[bytes]:
    """Never raises -- returns None (-> the contractual 404) on any failure,
    same contract as inspectors.get_preview_pdf()'s other branches.
    """
    try:
        cached = _cache.get(relpath, size, mtime, ".pdf")
        if cached:
            return cached
        out = _convert_with_soffice(path, data, kind, "pdf")
        if out:
            _cache.put(relpath, size, mtime, ".pdf", out)
        return out
    except Exception:  # noqa: BLE001
        return None


def _text_odt(path: Optional[Path], data: Optional[bytes]) -> str:
    from odf.opendocument import load
    from odf import table as odf_table, teletype
    from odf.namespaces import TABLENS, TEXTNS

    src = io.BytesIO(data) if data is not None else str(path)
    doc = load(src)
    lines: list[str] = []
    n_chars = 0
    for el in doc.text.childNodes:
        if n_chars > MAX_ODF_CHARS:
            lines.append(f"... truncated at {MAX_ODF_CHARS} characters")
            break
        qname = getattr(el, "qname", None)
        if qname == (TABLENS, "table"):
            rows_out = []
            for r_i, row in enumerate(el.getElementsByType(odf_table.TableRow)):
                if r_i >= MAX_TABLE_ROWS:
                    rows_out.append(f"... table truncated at {MAX_TABLE_ROWS} rows")
                    break
                cells = row.getElementsByType(odf_table.TableCell)
                rows_out.append(" | ".join(teletype.extractText(c).replace("\n", " ").strip() for c in cells))
            table_text = "\n".join(rows_out)
            lines.append("[table]")
            lines.append(table_text)
            n_chars += len(table_text)
        elif qname == (TEXTNS, "h"):
            level = el.getAttribute("outlinelevel") or "1"
            txt = teletype.extractText(el)
            line = f"{'#' * int(level)} {txt}"
            lines.append(line)
            n_chars += len(line)
        elif qname == (TEXTNS, "p"):
            txt = teletype.extractText(el)
            if txt.strip():
                lines.append(txt)
                n_chars += len(txt)
    return "\n".join(lines) if lines else "[no extractable text content]"


def _text_ods(path: Optional[Path], data: Optional[bytes]) -> str:
    from odf.opendocument import load
    from odf import table as odf_table, teletype

    src = io.BytesIO(data) if data is not None else str(path)
    doc = load(src)
    sheets = doc.spreadsheet.getElementsByType(odf_table.Table)
    lines = [f"worksheets: {len(sheets)} -> {', '.join(s.getAttribute('name') for s in sheets)}", ""]
    total_cells = 0
    for sheet in sheets:
        lines.append(f"--- sheet: {sheet.getAttribute('name')} ---")
        row_count = 0
        for row in sheet.getElementsByType(odf_table.TableRow):
            if row_count >= MAX_XLSX_ROWS_PER_SHEET or total_cells >= MAX_XLSX_TOTAL_CELLS:
                lines.append(f"... sheet truncated at {MAX_XLSX_ROWS_PER_SHEET} rows")
                break
            cells = row.getElementsByType(odf_table.TableCell)[:MAX_XLSX_COLS]
            texts = [teletype.extractText(c).strip() for c in cells]
            if not any(texts):
                continue
            lines.append(" | ".join(texts))
            row_count += 1
            total_cells += len(texts)
        lines.append("")
    return "\n".join(lines)


def _text_odp(path: Optional[Path], data: Optional[bytes]) -> str:
    from odf.opendocument import load
    from odf import draw as odf_draw, presentation as odf_presentation, teletype

    src = io.BytesIO(data) if data is not None else str(path)
    doc = load(src)
    pages = doc.presentation.getElementsByType(odf_draw.Page)
    lines: list[str] = []
    for i, page in enumerate(pages, start=1):
        if i > MAX_SLIDES:
            lines.append(f"... truncated at {MAX_SLIDES} slides")
            break
        lines.append(f"--- slide {i} ---")
        text = teletype.extractText(page)
        if text.strip():
            lines.append(text)
        for note in page.getElementsByType(odf_presentation.Notes):
            note_text = teletype.extractText(note)
            if note_text.strip():
                lines.append(f"[notes] {note_text}")
        lines.append("")
    return "\n".join(lines) if lines else "[no extractable slide content]"
