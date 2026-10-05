"""Anonymous document toolkit. All processing in RAM, nothing written to disk."""
import importlib.util
import io
import os
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

import fitz  # PyMuPDF
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import office

# The cap is read from the environment because the ceiling is not ours to pick:
# a platform in front of this app may refuse a body long before we see it.
# Vercel rejects any body over 4.5 MB before our code runs, so a build there
# that still promised 100 MB would advertise a limit the user can never reach
# and fail on a platform error page instead of our own message. Vercel sets
# VERCEL=1 itself, so the right default follows the host rather than depending
# on someone remembering to set a variable.
_PLATFORM_MB = 4 if os.environ.get("VERCEL") else 100
MAX_MB = int(os.environ.get("PDFCUY_MAX_MB") or _PLATFORM_MB)
MAX_BYTES = MAX_MB * 1024 * 1024
# A 1 MB file can hold thousands of pages, so bytes alone do not bound the work.
# Compressing 3000 pages took 86 seconds of CPU: a handful of such requests is a
# denial of service that never trips the size limit.
MAX_PAGES = 1500
# Merge accepted 400 files in a single request, each one a separate parse.
MAX_FILES = 50
STATIC = Path(__file__).parent / "static"

MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "zip": "application/zip",
    "png": "image/png",
    "jpg": "image/jpeg",
}

# Fields where an empty string genuinely means "not supplied": no password, no
# page filter, no pasted markup. Every other field has a real default, so a
# blank value means the client sent something broken.
#
# Watermark 'text' is deliberately absent. It defaults to CONFIDENTIAL, so a
# blank value used to stamp that word across someone's document even though
# they never typed it, while a single space returned an error. Same intent,
# two different outcomes, and the quiet one is the worse of the two.
BLANK_OK = frozenset({"password", "new_password", "pages", "remove", "html"})

async def no_blank_fields(request: Request):
    """Refuse empty values for fields that carry a default.

    Starlette hands an empty form value to FastAPI as absent, so Form("medium")
    quietly yields "medium" and pick() never sees the problem. A caller that
    posts level="" gets medium compression and no hint that their value was
    discarded, which is the silent fallback this project refuses everywhere
    else. Reading the form here is cheap: the body is already buffered, and the
    file parts stay readable afterwards.
    """
    if request.method != "POST":
        return
    try:
        form = await request.form()
    except Exception:
        return  # malformed bodies are the route's problem, not ours
    blank = sorted({
        k for k, v in form.multi_items()
        if isinstance(v, str) and not v.strip() and k not in BLANK_OK
    })
    if blank:
        names = ", ".join(blank)
        raise HTTPException(
            400,
            f"These settings arrived empty: {names}. Send a value or leave the "
            f"field out entirely to use the default.",
        )

app = FastAPI(
    title="PDFCUY", docs_url=None, redoc_url=None,
    dependencies=[Depends(no_blank_fields)],
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    """Lock the page down. CSP can be strict: no inline or remote JS is shipped."""
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    r.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    r.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    r.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), usb=(), payment=()",
    )
    r.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "form-action 'none'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
    )
    # The banner names the stack and version for anyone shopping for a CVE, and
    # gives a visitor nothing. Dropped here so it is gone under gunicorn too.
    if "server" in r.headers:
        del r.headers["server"]
    # HSTS only when the connection already arrived over TLS. Sending it on
    # plain HTTP is ignored by browsers anyway, and setting it unconditionally
    # would pin a developer's own machine to https://127.0.0.1, which serves
    # nothing. The forwarded header is what a terminating proxy reports.
    tls = (request.url.scheme == "https"
           or request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
           == "https")
    if tls:
        r.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains",
        )
    return r


# ---------- helpers ----------
def pick(value: str, allowed: dict, field: str):
    """Reject unknown enum values instead of silently using a default."""
    if value not in allowed:
        raise HTTPException(400, f"{field} must be one of: {', '.join(allowed)}")
    return allowed[value]



def in_range(value, lo, hi, field: str):
    """Reject out-of-range numbers instead of silently clamping them."""
    if value < lo or value > hi:
        raise HTTPException(400, f"{field} must be between {lo} and {hi}")
    return value


_UNSAFE = re.compile(r"[^\w.\-() ]+", re.UNICODE)
_ASCII_UNSAFE = re.compile(r"[^A-Za-z0-9._\-() ]+")


def safe_stem(name: str | None, fallback: str = "document") -> str:
    """Build a download name that cannot break the header or escape a directory.

    Drops directory parts, control characters, quotes and CR/LF, keeps unicode
    letters so non-Latin names survive, and caps the length.
    """
    raw = (name or "").replace("\\", "/").split("/")[-1]
    raw = Path(raw).stem
    raw = "".join(c for c in raw if c.isprintable() and not unicodedata.category(c).startswith("C"))
    raw = _UNSAFE.sub("_", raw).strip(" ._-")
    raw = re.sub(r"_{2,}", "_", raw)
    return raw[:80] or fallback


def disposition(name: str) -> str:
    """RFC 6266 Content-Disposition with an ASCII fallback plus a UTF-8 variant.

    The plain `filename` is pure ASCII so no byte can terminate the header early.
    `filename*` is percent-encoded, so clients still get the original characters.
    """
    stem, dot, ext = name.rpartition(".")
    stem = stem or name
    ext = _ASCII_UNSAFE.sub("", ext)[:10] if dot else ""
    ascii_stem = _ASCII_UNSAFE.sub("_", stem).strip(" ._-")
    ascii_stem = re.sub(r"_{2,}", "_", ascii_stem)[:80] or "document"
    plain = f"{ascii_stem}.{ext}" if ext else ascii_stem
    utf8 = quote(name, safe="")
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{utf8}"


async def grab(files: list[UploadFile], kinds=(b"%PDF",)) -> list[bytes]:
    if len(files) > MAX_FILES:
        raise HTTPException(
            413, f"That is {len(files)} files. Please send at most {MAX_FILES} "
                 f"in one request.")
    out, total = [], 0
    for f in files:
        data = await f.read()
        total += len(data)
        if total > MAX_BYTES:
            raise HTTPException(413, f"Total upload exceeds the {MAX_MB} MB limit")
        shown = safe_stem(f.filename, "The file")
        if not data:
            raise HTTPException(400, f"{shown} is empty")
        if kinds and not any(data.lstrip()[:5].startswith(k) for k in kinds):
            raise HTTPException(400, f"{shown} is not a valid PDF")
        out.append(data)
    if not out:
        raise HTTPException(400, "No file received")
    return out


def open_pdf(data: bytes, password: str = "") -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(400, "This PDF is damaged or unreadable")
    if doc.needs_pass and not doc.authenticate(password):
        raise HTTPException(401, "This PDF is password protected")
    if doc.page_count > MAX_PAGES:
        n = doc.page_count
        doc.close()
        raise HTTPException(
            413, f"This document has {n} pages, which is over the "
                 f"{MAX_PAGES}-page limit for one request. Split it first.")
    return doc


def ext_of(name: str | None) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def send(data: bytes, name: str, mime=None) -> StreamingResponse:
    mime = mime or MIME.get(ext_of(name), "application/octet-stream")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=mime,
        headers={
            "Content-Disposition": disposition(name),
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",
        },
    )


def scrub(doc: fitz.Document) -> None:
    """Drop the metadata the visible page never shows.

    A PDF carries the same information in several places at once. Redaction
    removed the glyphs from the page but left the name in the document title,
    the XMP packet, a sticky note, a link target and an embedded attachment, so
    the file still answered the question it was meant to stop answering.

    This runs on every PDF this service returns, not only redaction: handing
    back a file that quietly carries the author's name, the original filename
    or an attached payload is not what "stores nothing" should mean.
    """
    try:
        doc.set_metadata({})
    except Exception:
        pass
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
    for i in range(getattr(doc, "embfile_count", lambda: 0)() - 1, -1, -1):
        try:
            doc.embfile_del(i)
        except Exception:
            pass


def save(doc: fitz.Document, clean=True, strip=True) -> bytes:
    if strip:
        scrub(doc)
    buf = doc.tobytes(garbage=4, deflate=True, clean=clean) if clean else doc.tobytes()
    doc.close()
    return buf

def shrink_images(doc: fitz.Document, max_edge: int, quality: int) -> int:
    """Re-encode raster images as JPEG at a smaller size. Text and vectors untouched.

    Uses Page.replace_image, which rewrites the whole image object. Patching the
    stream by hand leaves /Filter and /ColorSpace inconsistent, which is why the
    earlier version shrank nothing on scanned files.
    """
    done = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        for info in page.get_images(full=True):
            xref = info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
            except Exception:
                continue  # unsupported codec (JBIG2, JPX): leave it alone
            try:
                if max(pix.width, pix.height) < 600:
                    continue  # small logos are not worth the quality loss
                if pix.alpha or pix.n > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                scale = min(1.0, max_edge / max(im.width, im.height))
                if scale < 1.0:
                    im = im.resize((max(1, int(im.width * scale)),
                                    max(1, int(im.height * scale))), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
                page.replace_image(xref, stream=buf.getvalue())
                done += 1
            except Exception:
                continue
            finally:
                pix = None
    return done


def parse_pages(spec: str, n: int) -> list[int]:
    """'1-3,7,9-' -> zero-based page indexes, deduped, ordered as written.

    An explicit page past the end of the document is an error, not something to
    drop quietly. Asking for page 99 of a 5-page file is a mistake worth saying
    out loud, otherwise the download looks like it worked and the missing page is
    only noticed later. Open ranges ('-3', '7-') are a deliberate shorthand and
    clamp to the document instead.
    """
    if not spec.strip():
        return list(range(n))
    seen, out, bad = set(), [], []
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            if not (m.group(1) or m.group(2)):
                raise HTTPException(400, f"Invalid page format: {part}")
            a = int(m.group(1) or 1)
            b = int(m.group(2) or n)
            # '5-2' is a deliberate reverse range, so judge the whole span
            # rather than the first number: on a 3-page file '9-2' is wrong, but
            # '5-2' on a 10-page file means pages 5,4,3,2 and must still work.
            if m.group(1) and m.group(2) and min(a, b) > n:
                bad.append(part)
                continue
            if m.group(1) and not m.group(2) and a > n:
                bad.append(part)
                continue
            a, b = max(1, min(a, n)), max(1, min(b, n))
        elif part.isdigit():
            a = b = int(part)
            if a < 1 or a > n:
                bad.append(part)
                continue
        else:
            raise HTTPException(400, f"Invalid page format: {part}")
        step = 1 if b >= a else -1
        for p in range(a, b + step, step):
            if 1 <= p <= n and p not in seen:
                seen.add(p)
                out.append(p - 1)
    if bad:
        # Only name the first few. A spec listing 4000 missing pages produced a
        # 23 KB error message, which is both unreadable and a free amplifier for
        # anyone sending junk.
        shown = ", ".join(bad[:5])
        more = f" and {len(bad) - 5} more" if len(bad) > 5 else ""
        raise HTTPException(
            400,
            f"This document has {n} page{'s' if n != 1 else ''}, so there is no "
            f"page {shown}{more}.",
        )
    if not out:
        raise HTTPException(400, "No pages matched that selection")
    return out


def zip_it(items: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in items:
            z.writestr(name, data)
    return buf.getvalue()


# ---------- routes ----------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/robots.txt", include_in_schema=False)
def robots():
    """Let the landing page be found; keep crawlers out of the tool endpoints.

    Without this a crawler gets a 404 and decides for itself. /api/ returns
    somebody's converted document, which has no business in an index.
    """
    return Response(
        "User-agent: *\nAllow: /$\nDisallow: /api/\n",
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/info")
async def info(file: UploadFile = File(...), password: str = Form("")):
    doc = open_pdf((await grab([file]))[0], password)
    r = {"pages": doc.page_count, "encrypted": doc.needs_pass}
    doc.close()
    return r


@app.post("/api/merge")
async def merge(files: list[UploadFile] = File(...), password: str = Form("")):
    datas = await grab(files)
    if len(datas) < 2:
        raise HTTPException(400, "Merging needs at least 2 PDFs")
    out = fitz.open()
    for d in datas:
        src = open_pdf(d, password)
        out.insert_pdf(src)
        src.close()
    return send(save(out), "merged.pdf")


@app.post("/api/split")
async def split(
    file: UploadFile = File(...),
    pages: str = Form(""),
    mode: str = Form("extract"),  # extract | each | ranges
    password: str = Form(""),
):
    pick(mode, {"extract": 0, "each": 1, "ranges": 2}, "Split mode")
    doc = open_pdf((await grab([file]))[0], password)
    stem = safe_stem(file.filename)
    try:
        if mode == "each":
            items = []
            for i in range(doc.page_count):
                one = fitz.open()
                one.insert_pdf(doc, from_page=i, to_page=i)
                items.append((f"{stem}_{i + 1}.pdf", save(one)))
            return send(zip_it(items), f"{stem}_pages.zip", "application/zip")

        if mode == "ranges":
            items = []
            for idx, part in enumerate(
                [p for p in re.split(r"[,\s]+", pages.strip()) if p], 1
            ):
                sel = parse_pages(part, doc.page_count)
                sub = fitz.open()
                sub.insert_pdf(doc, from_page=sel[0], to_page=sel[-1])
                items.append((f"{stem}_part{idx}.pdf", save(sub)))
            if not items:
                raise HTTPException(400, "Enter at least one page range")
            return send(zip_it(items), f"{stem}_split.zip", "application/zip")

        sel = parse_pages(pages, doc.page_count)
        out = fitz.open()
        for p in sel:
            out.insert_pdf(doc, from_page=p, to_page=p)
        return send(save(out), f"{stem}_extracted.pdf")
    finally:
        doc.close()


@app.post("/api/organize")
async def organize(
    file: UploadFile = File(...),
    pages: str = Form(""),      # new order, e.g. "3,1,2"
    remove: str = Form(""),     # pages to drop
    password: str = Form(""),
):
    doc = open_pdf((await grab([file]))[0], password)
    order = parse_pages(pages, doc.page_count)
    if remove.strip():
        drop = set(parse_pages(remove, doc.page_count))
        order = [p for p in order if p not in drop]
    if not order:
        raise HTTPException(400, "That would delete every page")
    out = fitz.open()
    for p in order:
        out.insert_pdf(doc, from_page=p, to_page=p)
    doc.close()
    return send(save(out), f"{safe_stem(file.filename)}_organized.pdf")


@app.post("/api/rotate")
async def rotate(
    file: UploadFile = File(...),
    angle: int = Form(90),
    pages: str = Form(""),
    password: str = Form(""),
):
    if angle % 90:
        raise HTTPException(400, "Angle must be a multiple of 90")
    doc = open_pdf((await grab([file]))[0], password)
    for p in parse_pages(pages, doc.page_count):
        page = doc[p]
        page.set_rotation((page.rotation + angle) % 360)
    return send(save(doc), f"{safe_stem(file.filename)}_rotated.pdf")


@app.post("/api/compress")
async def compress(
    file: UploadFile = File(...),
    level: str = Form("medium"),  # low | medium | high
    password: str = Form(""),
):
    raw = (await grab([file]))[0]
    max_edge, quality = pick(
        level,
        {"low": (2000, 80), "medium": (1500, 62), "high": (1000, 45)},
        "Compression level",
    )
    doc = open_pdf(raw, password)
    shrink_images(doc, max_edge, quality)
    scrub(doc)
    out = doc.tobytes(garbage=4, deflate=True, deflate_images=True,
                      deflate_fonts=True, clean=True)
    doc.close()
    if len(out) >= len(raw):  # never hand back something bigger
        out = raw
    return send(out, f"{safe_stem(file.filename)}_compressed.pdf")


@app.post("/api/pdf-to-images")
async def pdf_to_images(
    file: UploadFile = File(...),
    dpi: int = Form(150),
    fmt: str = Form("png"),
    pages: str = Form(""),
    password: str = Form(""),
):
    dpi = in_range(dpi, 36, 300, "DPI")
    fmt = "jpeg" if fmt.lower() in ("jpg", "jpeg") else "png"
    doc = open_pdf((await grab([file]))[0], password)
    stem = safe_stem(file.filename)
    sel = parse_pages(pages, doc.page_count)
    items = []
    for p in sel:
        pix = doc[p].get_pixmap(dpi=dpi, alpha=False)
        ext = "jpg" if fmt == "jpeg" else "png"
        items.append((f"{stem}_{p + 1}.{ext}", pix.tobytes(fmt)))
    doc.close()
    if len(items) == 1:
        name, data = items[0]
        return send(data, name, f"image/{fmt}")
    return send(zip_it(items), f"{stem}_images.zip", "application/zip")


@app.post("/api/images-to-pdf")
async def images_to_pdf(
    files: list[UploadFile] = File(...),
    size: str = Form("fit"),  # fit | a4
    margin: int = Form(0),
):
    datas = await grab(files, kinds=())
    out = fitz.open()
    for d in datas:
        try:
            im = Image.open(io.BytesIO(d))
            im.load()
        except Exception:
            raise HTTPException(400, "One of those files is not a valid image")
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        b = io.BytesIO()
        im.save(b, "JPEG", quality=90, optimize=True)
        img = b.getvalue()
        if size == "a4":
            page = out.new_page(width=595, height=842)
            rect = page.rect + (margin, margin, -margin, -margin)
        else:
            page = out.new_page(width=im.width, height=im.height)
            rect = page.rect
        page.insert_image(rect, stream=img, keep_proportion=True)
    return send(save(out), "images.pdf")


@app.post("/api/extract-text")
async def extract_text(
    file: UploadFile = File(...), pages: str = Form(""), password: str = Form("")
):
    doc = open_pdf((await grab([file]))[0], password)
    sel = parse_pages(pages, doc.page_count)
    chunks = [f"--- page {p + 1} ---\n{doc[p].get_text()}" for p in sel]
    doc.close()
    return send(
        "\n".join(chunks).encode("utf-8"),
        f"{safe_stem(file.filename)}.txt",
        "text/plain; charset=utf-8",
    )


WM_SPOTS = {
    "center": (0.5, 0.5), "top": (0.5, 0.12), "bottom": (0.5, 0.88),
    "top-left": (0.2, 0.12), "top-right": (0.8, 0.12),
    "bottom-left": (0.2, 0.88), "bottom-right": (0.8, 0.88),
}
# 3x3 lattice, used when tiling is on.
WM_TILES = [(x / 3 + 1 / 6, y / 3 + 1 / 6) for y in range(3) for x in range(3)]

@app.post("/api/watermark")
async def watermark(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    image: UploadFile = File(None),
    opacity: float = Form(0.18),
    fontsize: int = Form(48),
    angle: int = Form(0),
    place: str = Form("center"),
    tile: str = Form("off"),
    width: float = Form(40),
    pages: str = Form(""),
    password: str = Form(""),
):
    """Stamp text or an image across the chosen pages.

    An image takes priority when one is supplied: sending a logo and getting the
    default word 'CONFIDENTIAL' back would be baffling.

    Text is drawn with insert_text plus a morph matrix rather than insert_textbox,
    because insert_textbox only honours 90-degree steps and the diagonal stamp is
    the whole point of a watermark.
    """
    opacity = in_range(opacity, 0.03, 1.0, "Opacity")
    tiled = pick(tile, {"off": False, "on": True}, "Tile")
    angle = in_range(angle, -90, 90, "Angle")
    ax, ay = pick(place, WM_SPOTS, "Position")

    stamp = await image.read() if image is not None else b""
    if stamp:
        width = in_range(width, 5, 100, "Width")
        try:
            probe = Image.open(io.BytesIO(stamp))
            probe.verify()
            shape = Image.open(io.BytesIO(stamp))
            ratio = shape.height / shape.width
        except Exception:
            raise HTTPException(400, "The watermark image must be a PNG or JPG")
    else:
        text = text.strip()[:120]
        if not text:
            raise HTTPException(400, "Watermark text is empty")
        fontsize = in_range(fontsize, 8, 200, "Font size")

    raw = (await grab([file]))[0]
    if len(raw) + len(stamp) > MAX_BYTES:
        raise HTTPException(413, f"Total upload exceeds the {MAX_MB} MB limit")
    doc = open_pdf(raw, password)
    spots = WM_TILES if tiled else [(ax, ay)]

    for p in parse_pages(pages, doc.page_count):
        page = doc[p]
        r = page.rect
        if stamp:
            w = r.width * width / 100 / (3 if tiled else 1)
            h = w * ratio
            for cx, cy in spots:
                mid = fitz.Point(r.width * cx, r.height * cy)
                page.insert_image(
                    fitz.Rect(mid.x - w / 2, mid.y - h / 2,
                              mid.x + w / 2, mid.y + h / 2),
                    stream=stamp, keep_proportion=True, overlay=True,
                    rotate=0, alpha=-1,
                )
        else:
            size = fontsize if not tiled else max(8, fontsize // 3)
            font = fitz.Font("hebo")
            for cx, cy in spots:
                mid = fitz.Point(r.width * cx, r.height * cy)
                half = font.text_length(text, fontsize=size) / 2
                origin = fitz.Point(mid.x - half, mid.y + size * 0.35)
                morph = None
                if angle:
                    morph = (mid, fitz.Matrix(-angle))
                page.insert_text(
                    origin, text, fontsize=size, fontname="hebo",
                    color=(0.5, 0.5, 0.5), fill_opacity=opacity,
                    stroke_opacity=opacity, morph=morph, overlay=True,
                )
    return send(save(doc), f"{safe_stem(file.filename)}_watermarked.pdf")

@app.post("/api/flatten")
async def flatten(file: UploadFile = File(...), password: str = Form("")):
    """Bake form fields and annotations into the page content.

    After this, highlights and filled-in form values can no longer be edited or
    deleted by a reader, which is usually why a PDF is sent instead of the
    original document.
    """
    doc = open_pdf((await grab([file]))[0], password)
    live = sum(1 for p in doc for _ in p.widgets()) + \
        sum(1 for p in doc for _ in p.annots())
    if not live:
        doc.close()
        raise HTTPException(
            400, "This PDF has no form fields or annotations to flatten.")
    # bake() is the right primitive here. Re-drawing each page with
    # show_pdf_page looks correct but silently loses filled-in field values,
    # because a widget's text lives in its appearance stream rather than in the
    # page content, so the output would have looked flattened while quietly
    # throwing away the answers someone typed.
    doc.bake(annots=True, widgets=True)
    return send(save(doc), f"{safe_stem(file.filename)}_flattened.pdf")


@app.post("/api/protect")
async def protect(
    file: UploadFile = File(...),
    new_password: str = Form(...),
    password: str = Form(""),
    allow_print: bool = Form(True),
):
    if len(new_password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    doc = open_pdf((await grab([file]))[0], password)
    perm = int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_COPY)
    if allow_print:
        perm |= int(fitz.PDF_PERM_PRINT)
    scrub(doc)
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw=new_password,
        user_pw=new_password,
        permissions=perm,
        garbage=4,
        deflate=True,
    )
    doc.close()
    return send(data, f"{safe_stem(file.filename)}_protected.pdf")


@app.post("/api/unlock")
async def unlock(file: UploadFile = File(...), password: str = Form("")):
    data = (await grab([file]))[0]
    doc = open_pdf(data, password)
    if not doc.needs_pass and not doc.is_encrypted:
        doc.close()
        raise HTTPException(400, "This PDF is not password protected")
    scrub(doc)
    out = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE, garbage=4, deflate=True)
    doc.close()
    return send(out, f"{safe_stem(file.filename)}_unlocked.pdf")


# ---------- Office routes ----------
def _have_pdf2docx() -> bool:
    """Is the PDF to Word converter installed?

    pdf2docx pulls in OpenCV and NumPy, about 140 MB, which does not fit every
    deployment target. The client asks so it can hide the tool instead of
    offering a card that always fails.
    """
    return importlib.util.find_spec("pdf2docx") is not None


@app.get("/api/engines")
def engines():
    return {
        "libreoffice": bool(office.soffice()),
        "builtin": True,
        "pdf2docx": _have_pdf2docx(),
        "maxMb": MAX_MB,
        "maxPages": MAX_PAGES,
        "maxFiles": MAX_FILES,
    }


@app.post("/api/office-to-pdf")
async def office_to_pdf(files: list[UploadFile] = File(...), combine: str = Form("false")):
    merge_all = pick(combine, {"true": True, "false": False}, "Combine")
    datas = await grab(files, kinds=())
    outs, engines_used = [], set()
    for f, d in zip(files, datas):
        e = ext_of(f.filename)
        if e == "pdf":
            outs.append((f"{safe_stem(f.filename)}.pdf", d))
            engines_used.add("passthrough")
            continue
        try:
            pdf, eng = office.any_to_pdf(d, e)
        except office.ConvertError as err:
            raise HTTPException(422, f"{safe_stem(f.filename, 'That file')}: {err}")
        engines_used.add(eng)
        outs.append((f"{safe_stem(f.filename)}.pdf", pdf))

    if len(outs) == 1:
        name, data = outs[0]
        r = send(data, name, MIME["pdf"])
    elif merge_all:
        merged = fitz.open()
        for _, data in outs:
            src = fitz.open(stream=data, filetype="pdf")
            merged.insert_pdf(src)
            src.close()
        r = send(save(merged), "converted.pdf", MIME["pdf"])
    else:
        r = send(zip_it(outs), "converted.zip", MIME["zip"])
    r.headers["X-Engine"] = ",".join(sorted(engines_used))
    return r


@app.post("/api/pdf-to-xlsx")
async def pdf_to_xlsx(
    file: UploadFile = File(...), pages: str = Form(""), password: str = Form("")
):
    raw = (await grab([file]))[0]
    doc = open_pdf(raw, password)
    sel = parse_pages(pages, doc.page_count)
    doc.close()
    try:
        out = office.pdf_to_xlsx(raw, sel)
    except office.ConvertError as e:
        raise HTTPException(422, str(e))
    return send(out, f"{safe_stem(file.filename)}.xlsx", MIME["xlsx"])


@app.post("/api/pdf-to-pptx")
async def pdf_to_pptx(
    file: UploadFile = File(...),
    pages: str = Form(""),
    dpi: int = Form(120),
    password: str = Form(""),
):
    raw = (await grab([file]))[0]
    doc = open_pdf(raw, password)
    sel = parse_pages(pages, doc.page_count)
    doc.close()
    out = office.pdf_to_pptx(raw, sel, in_range(dpi, 72, 200, "DPI"))
    return send(out, f"{safe_stem(file.filename)}.pptx", MIME["pptx"])


@app.post("/api/office-text")
async def office_text(file: UploadFile = File(...)):
    data = (await grab([file], kinds=()))[0]
    try:
        txt = office.office_to_text(data, ext_of(file.filename))
    except office.ConvertError as e:
        raise HTTPException(422, str(e))
    return send(
        txt.encode("utf-8"), f"{safe_stem(file.filename)}.txt", MIME["txt"]
    )


@app.post("/api/convert")
async def convert(file: UploadFile = File(...), to: str = Form(...)):
    """Office<->Office via LibreOffice: docx->odt, xlsx->csv, doc->docx, etc."""
    to = to.lower().lstrip(".")
    if not re.fullmatch(r"[a-z0-9]{2,5}", to):
        raise HTTPException(400, "Invalid target format")
    data = (await grab([file], kinds=()))[0]
    src = ext_of(file.filename)
    if src == to:
        raise HTTPException(400, "Source and target formats are the same")
    if to == "pdf":
        try:
            out, eng = office.any_to_pdf(data, src)
        except office.ConvertError as e:
            raise HTTPException(422, str(e))
        r = send(out, f"{safe_stem(file.filename)}.pdf", MIME["pdf"])
        r.headers["X-Engine"] = eng
        return r
    if not office.soffice():
        raise HTTPException(
            501,
            f"Converting to .{to} requires LibreOffice on the server. "
            f"Without it the available targets are: pdf, txt, xlsx, pptx, docx (from PDF), png, jpg.",
        )
    try:
        out = office.via_soffice(data, src, to)
    except office.ConvertError as e:
        raise HTTPException(422, f"Conversion failed: {e}")
    return send(out, f"{safe_stem(file.filename)}.{to}")


@app.post("/api/pdf-to-docx")
async def pdf_to_docx(
    file: UploadFile = File(...), pages: str = Form(""), password: str = Form("")
):
    try:
        from pdf2docx import Converter  # heavy import, load on demand
    except ImportError:
        # pdf2docx pulls in OpenCV and NumPy, roughly 140 MB. Some deployment
        # targets cannot carry that, so it is optional rather than required.
        # Say which tool to use instead rather than returning a 500.
        raise HTTPException(
            501,
            "PDF to Word is not available in this deployment. Use PDF to text "
            "or PDF to Markdown, or run PDFCUY yourself where the converter "
            "is installed.",
        )

    raw = (await grab([file]))[0]
    doc = open_pdf(raw, password)
    sel = parse_pages(pages, doc.page_count)
    doc.close()
    # pdf2docx only works on paths: use an OS temp file, shredded in finally
    tmp = tempfile.mkdtemp(prefix="pdfx_")
    src, dst = os.path.join(tmp, "i.pdf"), os.path.join(tmp, "o.docx")
    try:
        with open(src, "wb") as fh:
            fh.write(raw)
        cv = Converter(src)
        try:
            cv.convert(dst, pages=sel)
        finally:
            cv.close()
        with open(dst, "rb") as fh:
            out = fh.read()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Conversion failed. The PDF is likely a scan with no text layer")
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    return send(out, f"{safe_stem(file.filename)}.docx", MIME["docx"])


# ---------- organize: dedicated remove / extract ----------

@app.post("/api/remove-pages")
async def remove_pages(
    file: UploadFile = File(...),
    pages: str = Form(...),
    password: str = Form(""),
):
    """Delete the listed pages and keep the rest."""
    if not pages.strip():
        raise HTTPException(400, "Tell us which pages to remove")
    doc = open_pdf((await grab([file]))[0], password)
    drop = set(parse_pages(pages, doc.page_count))
    keep = [i for i in range(doc.page_count) if i not in drop]
    if not keep:
        raise HTTPException(400, "That would delete every page")
    out = fitz.open()
    for p in keep:
        out.insert_pdf(doc, from_page=p, to_page=p)
    doc.close()
    return send(save(out), f"{safe_stem(file.filename)}_cleaned.pdf")

@app.post("/api/extract-pages")
async def extract_pages(
    file: UploadFile = File(...),
    pages: str = Form(...),
    password: str = Form(""),
):
    """Keep only the listed pages, in the order written."""
    if not pages.strip():
        raise HTTPException(400, "Tell us which pages to keep")
    doc = open_pdf((await grab([file]))[0], password)
    sel = parse_pages(pages, doc.page_count)
    if not sel:
        raise HTTPException(400, "No valid pages in that selection")
    out = fitz.open()
    for p in sel:
        out.insert_pdf(doc, from_page=p, to_page=p)
    doc.close()
    return send(save(out), f"{safe_stem(file.filename)}_extracted.pdf")

# ---------- edit: page numbers, crop ----------

@app.post("/api/page-numbers")
async def page_numbers(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    start: int = Form(1),
    fontsize: int = Form(10),
    fmt: str = Form("n"),
    pages: str = Form(""),
    password: str = Form(""),
):
    """Stamp page numbers at a chosen corner or centre."""
    xfrac, top = pick(position, {
        "bottom-center": (0.5, 0), "bottom-left": (0.0, 0), "bottom-right": (1.0, 0),
        "top-center": (0.5, 1), "top-left": (0.0, 1), "top-right": (1.0, 1),
    }, "Position")
    pick(fmt, {"n": 0, "n_of_total": 1, "page_n": 2}, "Number format")
    start = in_range(start, 0, 100000, "Start number")
    fontsize = in_range(fontsize, 6, 48, "Font size")
    doc = open_pdf((await grab([file]))[0], password)
    sel = parse_pages(pages, doc.page_count)
    total = len(sel)
    margin = fontsize * 2.2
    for seq, p in enumerate(sel):
        page = doc[p]
        r = page.rect
        num = start + seq
        label = {"n": f"{num}",
                 "n_of_total": f"{num} / {start + total - 1}",
                 "page_n": f"Page {num}"}[fmt]
        w = fitz.get_text_length(label, fontname="helv", fontsize=fontsize)
        x = margin + (r.width - 2 * margin - w) * xfrac
        y = margin if top else r.height - margin + fontsize
        page.insert_text((x, y), label, fontsize=fontsize,
                         fontname="helv", color=(0, 0, 0), overlay=True)
    return send(save(doc), f"{safe_stem(file.filename)}_numbered.pdf")

@app.post("/api/crop")
async def crop(
    file: UploadFile = File(...),
    top: float = Form(0),
    bottom: float = Form(0),
    left: float = Form(0),
    right: float = Form(0),
    pages: str = Form(""),
    password: str = Form(""),
):
    """Trim margins. Each value is a percentage cropped from that edge."""
    for nm, v in (("Top", top), ("Bottom", bottom), ("Left", left), ("Right", right)):
        in_range(v, 0, 45, nm)
    if top + bottom + left + right == 0:
        raise HTTPException(400, "Set at least one margin above zero")
    doc = open_pdf((await grab([file]))[0], password)
    for p in parse_pages(pages, doc.page_count):
        page = doc[p]
        r = page.rect
        box = fitz.Rect(
            r.x0 + r.width * left / 100, r.y0 + r.height * top / 100,
            r.x1 - r.width * right / 100, r.y1 - r.height * bottom / 100,
        )
        if box.width < 10 or box.height < 10:
            raise HTTPException(400, "Those margins leave almost nothing on the page")
        try:
            page.set_cropbox(box)
        except Exception:
            raise HTTPException(400, "This PDF rejects a smaller crop box")
    return send(save(doc), f"{safe_stem(file.filename)}_cropped.pdf")

# ---------- optimize: repair ----------

@app.post("/api/repair")
async def repair(file: UploadFile = File(...), password: str = Form("")):
    """Rebuild a damaged file. MuPDF reconstructs a broken xref table."""
    raw = (await grab([file]))[0]
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(422, "This file is too damaged to rebuild")
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise HTTPException(401, "This PDF is password protected")
    out = fitz.open()
    recovered = 0
    for i in range(doc.page_count):
        try:
            out.insert_pdf(doc, from_page=i, to_page=i)
            recovered += 1
        except Exception:
            continue
    doc.close()
    if recovered == 0:
        out.close()
        raise HTTPException(422, "No readable pages survived in this file")
    return send(save(out), f"{safe_stem(file.filename)}_repaired.pdf")

# ---------- security: redact, sign ----------

@app.post("/api/redact")
async def redact(
    file: UploadFile = File(...),
    words: str = Form(...),
    match_case: str = Form("false"),
    pages: str = Form(""),
    password: str = Form(""),
):
    """Permanently remove matching text, not merely cover it.

    apply_redactions deletes the underlying glyphs, so the words cannot be
    recovered by selecting or copying. A black rectangle alone would leave
    the text fully extractable underneath.

    Annotations and link targets that mention the same words go too. A PDF
    repeats its content in several places, and a file that still names the
    person in a sticky note has not been redacted in any useful sense.
    Document metadata and attachments are stripped from every response by
    scrub(), so they are already gone by the time this returns.
    """
    cased = pick(match_case, {"true": True, "false": False}, "Match case")
    terms = [w.strip() for w in words.splitlines() if w.strip()][:40]
    if not terms:
        raise HTTPException(400, "Enter at least one word or phrase to remove")
    doc = open_pdf((await grab([file]))[0], password)

    def mentions(text: str) -> bool:
        if not text:
            return False
        return any(t in text if cased else t.lower() in text.lower() for t in terms)

    hits = 0
    for p in parse_pages(pages, doc.page_count):
        page = doc[p]
        found = 0
        for term in terms:
            for area in page.search_for(term):
                # search_for is always case-insensitive, so when the user asked
                # for an exact match we re-read the glyphs inside the hit and
                # compare them ourselves.
                if cased and page.get_textbox(area).strip() != term:
                    continue
                page.add_redact_annot(area, fill=(0, 0, 0))
                found += 1
        if found:
            page.apply_redactions()
            hits += found
        # The same words are often repeated outside the page content, where
        # apply_redactions does not reach: a sticky note quoting the sentence,
        # or a link whose query string carries the name. Removing the text but
        # leaving those behind defeats the point of the tool.
        for an in list(page.annots() or []):
            info = an.info or {}
            if mentions(info.get("content", "")) or mentions(info.get("title", "")):
                try:
                    page.delete_annot(an)
                    hits += 1
                except Exception:
                    pass
        for lk in page.get_links():
            if mentions(lk.get("uri", "") or ""):
                try:
                    page.delete_link(lk)
                    hits += 1
                except Exception:
                    pass
    if hits == 0:
        doc.close()
        raise HTTPException(
            404, "None of those words were found. A scanned PDF has no text layer")
    return send(save(doc), f"{safe_stem(file.filename)}_redacted.pdf")

@app.post("/api/sign")
async def sign(
    file: UploadFile = File(...),
    image: UploadFile = File(...),
    page_no: int = Form(-1),
    corner: str = Form("bottom-right"),
    width: float = Form(30),
    password: str = Form(""),
):
    """Stamp a signature image onto a page. Not a cryptographic signature."""
    xr, yb = pick(corner, {
        "bottom-right": (1, 1), "bottom-left": (0, 1),
        "top-right": (1, 0), "top-left": (0, 0),
    }, "Corner")
    width = in_range(width, 5, 90, "Width")
    raw = (await grab([file]))[0]
    stamp = await image.read()
    if not stamp:
        raise HTTPException(400, "The signature image is empty")
    if len(raw) + len(stamp) > MAX_BYTES:
        raise HTTPException(413, f"Total upload exceeds the {MAX_MB} MB limit")
    try:
        probe = Image.open(io.BytesIO(stamp))
        probe.verify()
        probe = Image.open(io.BytesIO(stamp))
        ratio = probe.height / probe.width
    except Exception:
        raise HTTPException(400, "The signature must be a PNG or JPG image")
    doc = open_pdf(raw, password)
    idx = doc.page_count - 1 if page_no < 0 else in_range(
        page_no, 1, doc.page_count, "Page") - 1
    page = doc[idx]
    r = page.rect
    w = r.width * width / 100
    h = w * ratio
    pad = 24
    x0 = pad + (r.width - 2 * pad - w) * xr
    y0 = pad + (r.height - 2 * pad - h) * yb
    page.insert_image(fitz.Rect(x0, y0, x0 + w, y0 + h), stream=stamp, overlay=True)
    return send(save(doc), f"{safe_stem(file.filename)}_signed.pdf")

# ---------- convert: html, markdown ----------

@app.post("/api/html-to-pdf")
async def html_to_pdf(
    html: str = Form(""),
    file: UploadFile | None = File(None),
    size: str = Form("a4"),
):
    """Render pasted HTML, or an uploaded .html file, to PDF.

    Rendering is local via MuPDF Story. Remote images and stylesheets are
    deliberately not fetched: doing so would leak the reader's address to a
    third party, which defeats the point of this site.
    """
    pick(size, {"a4": 0, "letter": 1, "legal": 2}, "Page size")
    source = html
    name = "page"
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"Total upload exceeds the {MAX_MB} MB limit")
        if data:
            source = data.decode("utf-8", "replace")
            name = safe_stem(file.filename)
    if not source.strip():
        raise HTTPException(400, "Paste some HTML or choose a file")
    rect = fitz.paper_rect(size)
    try:
        story = fitz.Story(source)
        buf = io.BytesIO()
        writer = fitz.DocumentWriter(buf)
        more, guard = 1, 0
        while more and guard < 500:
            guard += 1
            dev = writer.begin_page(rect)
            more, _ = story.place(rect + (36, 36, -36, -36))
            story.draw(dev)
            writer.end_page()
        writer.close()
        out = buf.getvalue()
    except Exception:
        raise HTTPException(422, "That HTML could not be rendered")
    if not out:
        raise HTTPException(422, "That HTML produced an empty document")
    return send(out, f"{name}.pdf")

@app.post("/api/pdf-to-markdown")
async def pdf_to_markdown(
    file: UploadFile = File(...),
    pages: str = Form(""),
    password: str = Form(""),
):
    """Export text as Markdown, promoting larger type to headings."""
    doc = open_pdf((await grab([file]))[0], password)
    sel = parse_pages(pages, doc.page_count)
    sizes = []
    for p in sel:
        for blk in doc[p].get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    if sp["text"].strip():
                        sizes.append(round(sp["size"], 1))
    if not sizes:
        doc.close()
        raise HTTPException(422, "No text layer found. This looks like a scan")
    body = max(set(sizes), key=sizes.count)
    out = []
    for n, p in enumerate(sel):
        if n:
            out.append("\n---\n")
        for blk in doc[p].get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                spans = [s for s in ln.get("spans", []) if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans).strip()
                big = max(s["size"] for s in spans)
                bold = all("bold" in s["font"].lower() for s in spans)
                if big >= body * 1.6:
                    out.append(f"# {text}")
                elif big >= body * 1.25:
                    out.append(f"## {text}")
                elif big >= body * 1.1 or (bold and len(text) < 80):
                    out.append(f"### {text}")
                else:
                    out.append(text)
            out.append("")
    doc.close()
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    return send(md.encode("utf-8"), f"{safe_stem(file.filename)}.md",
                "text/markdown; charset=utf-8")

@app.middleware("http")
async def no_trace(request, call_next):
    resp = await call_next(request)
    # Tool output must never be indexed: a response here is somebody's document.
    # The landing page is different, it is public marketing and the whole point
    # of owning a domain, so it is left indexable. Anything under /api/ is a
    # user's file coming back out.
    if request.url.path.startswith("/api/"):
        resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="127.0.0.1", port=8000,
        access_log=False, server_header=False,
    )
