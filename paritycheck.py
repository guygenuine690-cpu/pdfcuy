"""Watermark upgrade, flatten, strict page specs, server banner."""
import io

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


def pdf(n=3, text="Body text"):
    d = pymupdf.open()
    for i in range(n):
        p = d.new_page()
        p.insert_text((72, 100), f"{text} {i + 1}", fontsize=13)
    b = d.tobytes()
    d.close()
    return b


def png(w=300, h=120, color=(10, 80, 200)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


def post(ep, files=None, data=None):
    return c.post(f"/api/{ep}", files=files or {}, data=data or {})


def f3():
    """Fresh 3-page fixture per call: an upload tuple cannot be re-read."""
    return ("doc.pdf", pdf(3), "application/pdf")

print("page spec no longer swallows impossible pages")
r = post("extract-pages", {"file": f3()}, {"pages": "1,99"})
chk("page 99 of a 3-page file is rejected", r.status_code == 400, r.status_code)
chk("error says the real page count", "3 pages" in r.text and "99" in r.text,
    r.json().get("detail", r.text)[:70])
r = post("extract-pages", {"file": f3()}, {"pages": "4-9"})
chk("fully out-of-range range rejected", r.status_code == 400, r.status_code)
r = post("extract-pages", {"file": f3()}, {"pages": "2-"})
chk("open-ended range still clamps", r.status_code == 200, r.status_code)
chk("clamped range gives 2 pages",
    pymupdf.open(stream=r.content, filetype="pdf").page_count == 2)
r = post("extract-pages", {"file": f3()}, {"pages": "-2"})
chk("leading-open range still clamps", r.status_code == 200, r.status_code)
r = post("extract-pages", {"file": f3()}, {"pages": "0"})
chk("page zero rejected", r.status_code == 400, r.status_code)
r = post("extract-pages", {"file": f3()}, {"pages": "-"})
chk("a lone dash is rejected", r.status_code == 400, r.status_code)
r = post("extract-pages", {"file": f3()}, {"pages": "2"})
chk("valid single page still works", r.status_code == 200, r.status_code)

print("\nwatermark: text angle and placement")
r = post("watermark", {"file": f3()}, {"text": "DRAFT", "angle": "45"})
chk("diagonal text accepted", r.status_code == 200, r.status_code)
d = pymupdf.open(stream=r.content, filetype="pdf")
chk("watermark text really on the page", "DRAFT" in d[0].get_text(),
    repr(d[0].get_text()[:40]))
d.close()
for a in ("-91", "91", "180"):
    r = post("watermark", {"file": f3()}, {"text": "X", "angle": a})
    chk(f"angle {a} rejected", r.status_code == 400, r.status_code)
r = post("watermark", {"file": f3()}, {"text": "X", "angle": "-90"})
chk("angle -90 allowed", r.status_code == 200, r.status_code)
r = post("watermark", {"file": f3()}, {"text": "X", "place": "middle-ish"})
chk("unknown position rejected", r.status_code == 400, r.status_code)
chk("position error lists the choices", "center" in r.text, r.text[:80])
for spot in ("center", "top", "bottom", "top-left", "bottom-right"):
    r = post("watermark", {"file": f3()}, {"text": "X", "place": spot})
    chk(f"position {spot} works", r.status_code == 200, r.status_code)

print("\nwatermark: tiling")
r = post("watermark", {"file": f3()}, {"text": "COPY", "tile": "on"})
chk("tiled text accepted", r.status_code == 200, r.status_code)
d = pymupdf.open(stream=r.content, filetype="pdf")
chk("tiling repeats the word 9 times", d[0].get_text().count("COPY") == 9,
    f"{d[0].get_text().count('COPY')} copies")
d.close()
r = post("watermark", {"file": f3()}, {"text": "X", "tile": "maybe"})
chk("bad tile value rejected", r.status_code == 400, r.status_code)

print("\nwatermark: image")
r = post("watermark",
         {"file": f3(), "image": ("logo.png", png(), "image/png")},
         {"width": "30"})
chk("image watermark accepted", r.status_code == 200, r.status_code)
d = pymupdf.open(stream=r.content, filetype="pdf")
chk("image embedded on every page",
    all(len(d[i].get_images()) == 1 for i in range(3)))
chk("default text not also stamped", "CONFIDENTIAL" not in d[0].get_text(),
    "image took priority")
d.close()
r = post("watermark",
         {"file": f3(), "image": ("logo.png", png(), "image/png")},
         {"tile": "on", "width": "40"})
d = pymupdf.open(stream=r.content, filetype="pdf")
chk("tiled image placed 9 times", len(d[0].get_images()) == 9,
    f"{len(d[0].get_images())} placements")
d.close()
r = post("watermark",
         {"file": f3(), "image": ("x.png", b"not an image", "image/png")},
         {})
chk("corrupt image rejected", r.status_code == 400, r.status_code)
chk("corrupt image error is readable", "PNG or JPG" in r.text, r.text[:70])
r = post("watermark",
         {"file": f3(), "image": ("logo.png", png(), "image/png")},
         {"width": "150"})
chk("over-wide image rejected", r.status_code == 400, r.status_code)
r = post("watermark", {"file": f3()}, {"text": "   "})
chk("blank text still rejected", r.status_code == 400, r.status_code)

print("\nflatten")
r = post("flatten", {"file": ("plain.pdf", pdf(2), "application/pdf")})
chk("plain PDF told there is nothing to flatten", r.status_code == 400,
    r.status_code)
chk("flatten error explains why",
    "no form fields or annotations" in r.text, r.json().get("detail", "")[:60])

d = pymupdf.open()
p = d.new_page()
p.insert_text((72, 100), "Signed by:", fontsize=12)
w = pymupdf.Widget()
w.field_name = "who"
w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
w.rect = pymupdf.Rect(150, 85, 320, 105)
w.field_value = "Ada Lovelace"
p.add_widget(w)
p2 = d.new_page()
p2.insert_text((72, 100), "Reviewed", fontsize=12)
p2.add_highlight_annot(pymupdf.Rect(70, 88, 140, 106))
form = d.tobytes()
d.close()

src = pymupdf.open(stream=form, filetype="pdf")
chk("fixture really has a widget", sum(1 for _ in src[0].widgets()) == 1)
chk("fixture really has an annotation", sum(1 for _ in src[1].annots()) == 1)
src.close()

r = post("flatten", {"file": ("form.pdf", form, "application/pdf")})
chk("form PDF flattens", r.status_code == 200, r.status_code)
d = pymupdf.open(stream=r.content, filetype="pdf")
chk("no widgets survive", sum(1 for p in d for _ in p.widgets()) == 0)
chk("no annotations survive", sum(1 for p in d for _ in p.annots()) == 0)
chk("filled value is now permanent text", "Ada Lovelace" in d[0].get_text(),
    repr(d[0].get_text()[:40]))
chk("page count unchanged", d.page_count == 2, d.page_count)
chk("named _flattened", "flattened" in
    r.headers["content-disposition"], r.headers["content-disposition"][:60])
d.close()

print("\nserver banner")
for path, kw in (("/", {}), ("/static/app.css", {})):
    r = c.get(path, **kw)
    chk(f"no Server header on {path}", "server" not in
        {k.lower() for k in r.headers}, r.headers.get("server", "absent"))
r = post("extract-pages", {"file": f3()}, {"pages": "99"})
chk("no Server header on an error body",
    "server" not in {k.lower() for k in r.headers},
    r.headers.get("server", "absent"))

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("PARITY OK")
