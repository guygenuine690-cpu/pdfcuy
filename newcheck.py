"""Exercise the 8 new endpoints end to end."""
import io
import random
import zipfile

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

import app as A

c = TestClient(A.app)
ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


d = pymupdf.open()
for i in range(6):
    p = d.new_page()
    p.insert_text((72, 90), f"Heading {i + 1}", fontsize=22)
    p.insert_text((72, 140), "Body text with SECRET-ALPHA inside it.", fontsize=11)
PDF = d.tobytes()
d.close()
F = lambda: {"file": ("doc.pdf", PDF, "application/pdf")}


def pages_of(b):
    x = pymupdf.open(stream=b, filetype="pdf")
    n = x.page_count
    x.close()
    return n


print("remove pages")
r = c.post("/api/remove-pages", files=F(), data={"pages": "2,4"})
chk("drops two pages", r.status_code == 200 and pages_of(r.content) == 4,
    f"{r.status_code} {pages_of(r.content) if r.status_code == 200 else r.text[:50]}")
r = c.post("/api/remove-pages", files=F(), data={"pages": "1-"})
chk("refuses to empty the file", r.status_code == 400, r.text[:60])
r = c.post("/api/remove-pages", files=F(), data={"pages": ""})
chk("requires a selection", r.status_code in (400, 422), r.text[:50])

print("extract pages")
r = c.post("/api/extract-pages", files=F(), data={"pages": "5,1,3"})
chk("keeps three pages", r.status_code == 200 and pages_of(r.content) == 3)
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    first = x[0].get_text()
    x.close()
    chk("honours the written order", "Heading 5" in first, repr(first[:18]))

print("page numbers")
for pos in ("bottom-center", "top-left", "bottom-right", "top-right"):
    r = c.post("/api/page-numbers", files=F(), data={"position": pos})
    chk(f"stamps at {pos}", r.status_code == 200, r.text[:50])
r = c.post("/api/page-numbers", files=F(), data={"fmt": "n_of_total", "start": "1"})
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    t = x[0].get_text()
    x.close()
    chk("renders 'n / total'", "1 / 6" in t, repr(t[-14:]))
r = c.post("/api/page-numbers", files=F(), data={"position": "middle"})
chk("bad position rejected", r.status_code == 400 and "one of" in r.text, r.text[:60])
r = c.post("/api/page-numbers", files=F(), data={"fontsize": "99"})
chk("huge font rejected", r.status_code == 400, r.text[:50])

print("crop")
base = pymupdf.open(stream=PDF, filetype="pdf")
FULL_H = base[0].rect.height  # PyMuPDF pages default to A4, not Letter
base.close()
r = c.post("/api/crop", files=F(), data={"top": "10", "bottom": "10"})
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    h = x[0].rect.height
    x.close()
    want = FULL_H * 0.8
    chk("page is 20 percent shorter", abs(h - want) < 2,
        f"{FULL_H:.0f}pt -> {h:.0f}pt (want {want:.0f})")
else:
    chk("page is 20 percent shorter", False, r.text[:60])
r = c.post("/api/crop", files=F(), data={})
chk("needs one margin", r.status_code == 400, r.text[:55])
r = c.post("/api/crop", files=F(), data={"left": "60"})
chk("over-crop rejected", r.status_code == 400, r.text[:55])

print("repair")
broken = bytearray(PDF)
ix = broken.rfind(b"startxref")
broken[ix:ix + 9] = b"startxr3f"
r = c.post("/api/repair", files={"file": ("bad.pdf", bytes(broken), "application/pdf")})
chk("rebuilds a broken xref", r.status_code == 200 and pages_of(r.content) == 6,
    f"{r.status_code}")
r = c.post("/api/repair", files={"file": ("x.pdf", b"%PDF-1.7 total garbage", "application/pdf")})
chk("hopeless file refused", r.status_code in (400, 422), r.text[:55])

print("redact")
r = c.post("/api/redact", files=F(), data={"words": "SECRET-ALPHA"})
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    leftover = "".join(pg.get_text() for pg in x)
    x.close()
    chk("text is really gone, not covered", "SECRET-ALPHA" not in leftover,
        "no trace" if "SECRET-ALPHA" not in leftover else "STILL EXTRACTABLE")
    chk("other text survives", "Body text" in leftover)
else:
    chk("text is really gone, not covered", False, r.text[:60])
r = c.post("/api/redact", files=F(), data={"words": "secret-alpha"})
chk("case-insensitive by default", r.status_code == 200, r.text[:50])
r = c.post("/api/redact", files=F(), data={"words": "secret-alpha", "match_case": "true"})
chk("match_case respects case", r.status_code == 404, r.text[:55])
r = c.post("/api/redact", files=F(), data={"words": "nowhere-in-doc"})
chk("no match explains why", r.status_code == 404 and "scan" in r.text.lower(), r.text[:70])
r = c.post("/api/redact", files=F(), data={"words": "   "})
chk("blank term rejected", r.status_code == 400, r.text[:50])

print("sign")
sb = io.BytesIO()
Image.new("RGB", (300, 120), (10, 20, 90)).save(sb, "PNG")
SIG = sb.getvalue()
r = c.post("/api/sign", files={"file": ("doc.pdf", PDF, "application/pdf"),
                               "image": ("sig.png", SIG, "image/png")})
chk("stamps on the last page", r.status_code == 200, r.text[:60])
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    chk("image lands on final page", len(x[x.page_count - 1].get_images()) == 1,
        f"{len(x[x.page_count-1].get_images())} imgs")
    chk("earlier pages untouched", len(x[0].get_images()) == 0)
    x.close()
r = c.post("/api/sign", files={"file": ("doc.pdf", PDF, "application/pdf"),
                               "image": ("sig.png", SIG, "image/png")},
           data={"page_no": "2", "corner": "top-left"})
chk("targets a chosen page", r.status_code == 200, r.text[:50])
r = c.post("/api/sign", files={"file": ("doc.pdf", PDF, "application/pdf"),
                               "image": ("sig.txt", b"not an image", "text/plain")})
chk("non-image rejected", r.status_code == 400, r.text[:55])
r = c.post("/api/sign", files={"file": ("doc.pdf", PDF, "application/pdf"),
                               "image": ("sig.png", SIG, "image/png")},
           data={"page_no": "99"})
chk("page past the end rejected", r.status_code == 400, r.text[:55])

print("html to pdf")
r = c.post("/api/html-to-pdf",
           data={"html": "<h1>Invoice</h1><p>Line one</p><ul><li>a</li><li>b</li></ul>"})
chk("renders pasted html", r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:55])
if r.status_code == 200:
    x = pymupdf.open(stream=r.content, filetype="pdf")
    t = x[0].get_text()
    x.close()
    chk("heading and list made it", "Invoice" in t and "Line one" in t, repr(t[:34]))
r = c.post("/api/html-to-pdf", files={"file": ("page.html", b"<h2>From a file</h2>", "text/html")})
chk("accepts an uploaded file", r.status_code == 200, r.text[:50])
r = c.post("/api/html-to-pdf", data={"html": "   "})
chk("empty html rejected", r.status_code == 400, r.text[:50])
r = c.post("/api/html-to-pdf", data={"html": "<p>x</p>", "size": "poster"})
chk("bad page size rejected", r.status_code == 400, r.text[:55])

print("pdf to markdown")
r = c.post("/api/pdf-to-markdown", files=F())
if r.status_code == 200:
    md = r.content.decode()
    chk("headings become markdown", "# Heading 1" in md, repr(md[:22]))
    chk("body stays plain", "Body text with" in md)
    chk("pages separated by a rule", md.count("---") >= 4, f"{md.count('---')} rules")
else:
    chk("headings become markdown", False, r.text[:60])
blank = pymupdf.open()
blank.new_page()
nb = blank.tobytes()
blank.close()
r = c.post("/api/pdf-to-markdown", files={"file": ("blank.pdf", nb, "application/pdf")})
chk("scan without text explained", r.status_code == 422 and "scan" in r.text.lower(),
    r.text[:60])

print("compress actually compresses now")
random.seed(5)
img = Image.new("RGB", (1700, 1200))
px = img.load()
for y in range(0, 1200, 4):
    for x in range(0, 1700, 4):
        col = (random.randint(60, 200), random.randint(60, 200), random.randint(80, 210))
        for dy in range(4):
            for dx in range(4):
                if x + dx < 1700 and y + dy < 1200:
                    px[x + dx, y + dy] = col
jb = io.BytesIO()
img.save(jb, "JPEG", quality=95)
hd = pymupdf.open()
for _ in range(3):
    pg = hd.new_page()
    pg.insert_image(pg.rect, stream=jb.getvalue())
    pg.insert_text((60, 60), "Scanned page", fontsize=13)
HEAVY = hd.tobytes()
hd.close()
prev = None
for lv in ("low", "medium", "high"):
    r = c.post("/api/compress", files={"file": ("scan.pdf", HEAVY, "application/pdf")},
               data={"level": lv})
    pct = 100 - len(r.content) * 100 / len(HEAVY)
    chk(f"{lv} shrinks a scan", r.status_code == 200 and pct > 35,
        f"{len(HEAVY)//1024}KB -> {len(r.content)//1024}KB ({pct:+.0f}%)")
    if prev is not None:
        chk(f"{lv} is smaller than the weaker level", len(r.content) < prev)
    prev = len(r.content)
    x = pymupdf.open(stream=r.content, filetype="pdf")
    chk(f"{lv} output still opens with text", x.page_count == 3
        and "Scanned page" in x[0].get_text())
    x.close()

print(f"\n{ok} passed, {fail} failed")
assert fail == 0
print("NEW TOOLS OK")
