"""Office <-> PDF. Uses LibreOffice when installed, pure-Python fallback otherwise."""
import csv
import io
import os
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path

# ---------- LibreOffice discovery (cached once per process) ----------
_SOFFICE = "unset"


def soffice() -> str | None:
    global _SOFFICE
    if _SOFFICE == "unset":
        cand = [os.environ.get("SOFFICE_BIN", "")] + [
            shutil.which(n) or "" for n in ("soffice", "soffice.exe", "libreoffice")
        ] + [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            "/usr/bin/soffice",
            "/usr/lib/libreoffice/program/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
        _SOFFICE = next((p for p in cand if p and os.path.isfile(p)), None)
    return _SOFFICE


class ConvertError(Exception):
    pass


def via_soffice(data: bytes, src_ext: str, target: str, timeout=180) -> bytes:
    """target: 'pdf', 'docx', 'xlsx', 'csv', ... Returns converted bytes."""
    exe = soffice()
    if not exe:
        raise ConvertError("no-soffice")
    tmp = tempfile.mkdtemp(prefix="off_")
    src = os.path.join(tmp, f"in.{src_ext}")
    try:
        with open(src, "wb") as fh:
            fh.write(data)
        # -env:UserInstallation isolates the profile so concurrent runs don't collide
        p = subprocess.run(
            [exe, f"-env:UserInstallation=file:///{tmp.replace(os.sep, '/')}/prof",
             "--headless", "--norestore", "--invisible", "--nolockcheck",
             "--convert-to", target, "--outdir", tmp, src],
            capture_output=True, timeout=timeout,
        )
        ext = target.split(":")[0]
        out = Path(tmp) / f"in.{ext}"
        if not out.is_file():
            raise ConvertError((p.stderr or p.stdout).decode("utf8", "replace")[:200] or "empty output")
        return out.read_bytes()
    except subprocess.TimeoutExpired:
        raise ConvertError("timeout")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- pure-Python fallback: anything -> PDF ----------
def _pdf_doc(buf, title=""):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buf, pagesize=A4, title=title,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )


def _styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Cell", parent=s["BodyText"], fontSize=8, leading=9.6, spaceAfter=0))
    return s


def _grid(rows, styles, max_cols=14):
    """rows: list[list[str]] -> reportlab Table sized to the frame."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = [r[:max_cols] for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    rows = [list(r) + [""] * (ncol - len(r)) for r in rows]
    body = [[Paragraph(escape(str(c))[:600], styles["Cell"]) for c in r] for r in rows]
    w = (A4[0] - 36 * mm) / ncol
    t = Table(body, colWidths=[w] * ncol, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b9c0cc")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def docx_to_pdf(data: bytes) -> bytes:
    import docx
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    d = docx.Document(io.BytesIO(data))
    st = _styles()
    flow = []
    for block in _docx_blocks(d):
        if block[0] == "p":
            txt, style = block[1], block[2]
            if not txt.strip():
                flow.append(Spacer(1, 6))
                continue
            key = "Heading1" if style.startswith("Heading 1") or style == "Title" else \
                  "Heading2" if style.startswith("Heading 2") else \
                  "Heading3" if style.startswith("Heading") else "BodyText"
            flow.append(Paragraph(escape(txt), st[key]))
        else:
            t = _grid(block[1], st)
            if t:
                flow += [Spacer(1, 6), KeepTogether(t), Spacer(1, 8)]
    if not flow:
        flow = [Paragraph("(empty document)", st["BodyText"])]
    buf = io.BytesIO()
    _pdf_doc(buf).build(flow)
    return buf.getvalue()


def _docx_blocks(d):
    """Yield paragraphs and tables in true document order."""
    from docx.table import Table as DT
    from docx.text.paragraph import Paragraph as DP

    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = DP(child, d)
            yield ("p", p.text, p.style.name if p.style is not None else "Normal")
        elif tag == "tbl":
            t = DT(child, d)
            yield ("t", [[c.text for c in row.cells] for row in t.rows])


def xlsx_to_pdf(data: bytes) -> bytes:
    import openpyxl
    from reportlab.platypus import PageBreak, Paragraph, Spacer

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    st = _styles()
    flow = []
    for i, ws in enumerate(wb.worksheets):
        if i:
            flow.append(PageBreak())
        flow += [Paragraph(escape(ws.title), st["Heading2"]), Spacer(1, 5)]
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else v for v in r])
            if len(rows) >= 2000:  # ponytail: hard cap; paginate if huge sheets matter
                break
        t = _grid(rows, st, max_cols=18)
        flow.append(t if t else Paragraph("(empty sheet)", st["BodyText"]))
    wb.close()
    buf = io.BytesIO()
    _pdf_doc(buf).build(flow)
    return buf.getvalue()


def pptx_to_pdf(data: bytes) -> bytes:
    from pptx import Presentation
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    prs = Presentation(io.BytesIO(data))
    st = _styles()
    flow = []
    for i, slide in enumerate(prs.slides, 1):
        if i > 1:
            flow.append(PageBreak())
        flow.append(Paragraph(f"Slide {i}", st["Heading3"]))
        for sh in slide.shapes:
            if sh.has_text_frame:
                for para in sh.text_frame.paragraphs:
                    txt = "".join(r.text for r in para.runs).strip()
                    if txt:
                        flow.append(Paragraph(escape(txt), st["BodyText"]))
            elif sh.has_table:
                t = _grid([[c.text for c in r.cells] for r in sh.table.rows], st)
                if t:
                    flow += [Spacer(1, 5), t, Spacer(1, 5)]
        flow.append(Spacer(1, 4))
    buf = io.BytesIO()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
    ).build(flow or [Paragraph("(empty presentation)", st["BodyText"])])
    return buf.getvalue()


def text_to_pdf(data: bytes, is_csv=False) -> bytes:
    from reportlab.platypus import Paragraph, Preformatted

    txt = data.decode("utf-8", "replace").replace("\r\n", "\n").lstrip("\ufeff")
    st = _styles()
    if is_csv:
        rows = list(csv.reader(io.StringIO(txt)))
        flow = [_grid(rows, st, max_cols=18) or Paragraph("(empty)", st["BodyText"])]
    else:
        flow = [Preformatted(ln or " ", st["Code"]) for ln in txt.split("\n")[:4000]]
    buf = io.BytesIO()
    _pdf_doc(buf).build(flow)
    return buf.getvalue()


EXT_TO_PDF = {
    "docx": docx_to_pdf, "xlsx": xlsx_to_pdf, "pptx": pptx_to_pdf,
    "txt": text_to_pdf, "md": text_to_pdf, "csv": lambda d: text_to_pdf(d, True),
}
LEGACY = {"doc", "xls", "ppt", "odt", "ods", "odp", "rtf", "html", "htm", "pages", "numbers", "key"}


def any_to_pdf(data: bytes, ext: str) -> tuple[bytes, str]:
    """Returns (pdf_bytes, engine_used)."""
    ext = ext.lower().lstrip(".")
    if soffice():
        try:
            return via_soffice(data, ext, "pdf"), "libreoffice"
        except ConvertError:
            pass  # fall through to pure-python
    if ext in EXT_TO_PDF:
        try:
            return EXT_TO_PDF[ext](data), "builtin"
        except Exception as e:
            raise ConvertError(f"could not read {ext}: {type(e).__name__}")
    if ext in LEGACY:
        raise ConvertError(
            f"Format .{ext} requires LibreOffice. Install LibreOffice and restart the server, "
            f"or re-save the file as .docx, .xlsx, or .pptx."
        )
    raise ConvertError(f"Format .{ext} is not supported")


# ---------- PDF -> Office (pure-Python) ----------
def pdf_to_xlsx(data: bytes, pages: list[int]) -> bytes:
    import openpyxl
    import pdfplumber
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    found = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for p in pages:
            if p >= len(pdf.pages):
                continue
            page = pdf.pages[p]
            tables = page.extract_tables() or []
            if not tables:
                # no ruled table: fall back to whitespace-separated rows
                tables = [[[ln] for ln in (page.extract_text() or "").split("\n") if ln.strip()]]
                if not tables[0]:
                    continue
            for ti, tb in enumerate(tables, 1):
                ws = wb.create_sheet(f"H{p + 1}" + (f"_T{ti}" if len(tables) > 1 else ""))
                widest = {}
                for r in tb:
                    row = [("" if c is None else str(c).replace("\n", " ")) for c in r]
                    ws.append(row)
                    for ci, v in enumerate(row, 1):
                        widest[ci] = min(60, max(widest.get(ci, 9), len(v) + 2))
                for ci, w in widest.items():
                    ws.column_dimensions[get_column_letter(ci)].width = w
                ws.freeze_panes = "A2"
                found += 1
    if not found:
        raise ConvertError("No text or tables detected. This PDF is likely a scan")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf_to_pptx(data: bytes, pages: list[int], dpi=120) -> bytes:
    import fitz
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation()
    blank = prs.slide_layouts[6]
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        first = doc[pages[0]].rect
        prs.slide_width = Emu(int(first.width * 12700))
        prs.slide_height = Emu(int(first.height * 12700))
        for p in pages:
            pg = doc[p]
            img = pg.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
            s = prs.slides.add_slide(blank)
            s.shapes.add_picture(
                io.BytesIO(img), 0, 0,
                width=Emu(int(pg.rect.width * 12700)), height=Emu(int(pg.rect.height * 12700)),
            )
    finally:
        doc.close()
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def office_to_text(data: bytes, ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext == "docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        out = []
        for b in _docx_blocks(d):
            out.append(b[1] if b[0] == "p" else
                       "\n".join("\t".join(r) for r in b[1]))
        return "\n".join(out)
    if ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"--- {ws.title} ---")
            for r in ws.iter_rows(values_only=True):
                out.append("\t".join("" if v is None else str(v) for v in r))
        wb.close()
        return "\n".join(out)
    if ext == "pptx":
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        out = []
        for i, s in enumerate(prs.slides, 1):
            out.append(f"--- Slide {i} ---")
            out += [sh.text_frame.text for sh in s.shapes if sh.has_text_frame]
        return "\n".join(out)
    if ext in ("txt", "md", "csv"):
        return data.decode("utf-8", "replace")
    raise ConvertError(f"Text extraction for .{ext} is not supported")
