"""Security regressions: resource caps and metadata stripping."""
import pymupdf
from fastapi.testclient import TestClient

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


def pages(n, text="body"):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 100), f"{text} {i + 1}", fontsize=10)
    b = d.tobytes()
    d.close()
    return b


def detail(r):
    try:
        return r.json().get("detail", "")
    except Exception:
        return r.text[:90]


print("page-count cap bounds the work that bytes do not")
r = c.post("/api/compress", files={"file": ("d.pdf", pages(20), "application/pdf")})
chk("a normal document passes", r.status_code == 200, r.status_code)
big = pages(A.MAX_PAGES + 50)
r = c.post("/api/compress", files={"file": ("d.pdf", big, "application/pdf")})
d = detail(r)
chk("an oversized page count is refused", r.status_code == 413, f"{r.status_code}")
chk("the limit is stated", str(A.MAX_PAGES) in d, d[:80])
chk("it suggests what to do", "split" in d.lower(), d[:80])
chk("the refusal is cheap", len(big) < 2_000_000, f"{len(big) // 1024}KB triggered it")

print("\nfile-count cap")
one = pages(1)
r = c.post("/api/merge", files=[("files", (f"{i}.pdf", one, "application/pdf"))
                                for i in range(3)])
chk("a few files merge fine", r.status_code == 200, r.status_code)
r = c.post("/api/merge", files=[("files", (f"{i}.pdf", one, "application/pdf"))
                                for i in range(A.MAX_FILES + 10)])
d = detail(r)
chk("too many files is refused", r.status_code == 413, r.status_code)
chk("the count and limit are named",
    str(A.MAX_FILES) in d and str(A.MAX_FILES + 10) in d, d[:90])

print("\nhidden copies of the content are stripped from every response")


def loaded():
    """A document that repeats its secret in the places pages do not show."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), "visible SECRET text", fontsize=12)
    d.set_metadata({"title": "SECRET", "author": "SECRET", "keywords": "SECRET"})
    d.embfile_add("payload.bin", b"SECRET-ATTACHMENT-BODY")
    try:
        d.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                           "<dc:creator>SECRET</dc:creator></x:xmpmeta>")
    except Exception:
        pass
    b = d.tobytes()
    d.close()
    return b


SRC = loaded()
chk("the sample really is loaded", b"SECRET-ATTACHMENT-BODY" in SRC)

for ep, data in (("compress", {"level": "low"}), ("rotate", {"angle": "90"}),
                 ("extract-pages", {"pages": "1"}),
                 ("watermark", {"text": "X"}), ("page-numbers", None),
                 ("repair", None)):
    r = c.post(f"/api/{ep}", files={"file": ("d.pdf", SRC, "application/pdf")},
               data=data)
    if r.status_code != 200:
        print(f"  skip  {ep} -> {r.status_code} {detail(r)[:50]}")
        continue
    d = pymupdf.open(stream=r.content, filetype="pdf")
    meta = any("SECRET" in str(v) for v in (d.metadata or {}).values())
    try:
        xmp = bool(d.get_xml_metadata()) and "SECRET" in d.get_xml_metadata()
    except Exception:
        xmp = False
    emb = d.embfile_count()
    d.close()
    chk(f"{ep}: no metadata, no xmp, no attachment",
        not meta and not xmp and emb == 0,
        f"meta={meta} xmp={xmp} embedded={emb}")
    chk(f"{ep}: attachment body is gone from the bytes",
        b"SECRET-ATTACHMENT-BODY" not in r.content)

print("\nflatten and unlock need their own preconditions, so build them")
# flatten refuses a file with nothing to bake, and unlock refuses one that is
# not encrypted. Both still have to strip the hidden copies, so give each the
# input it actually requires rather than skipping the check.
d = pymupdf.open()
p = d.new_page()
p.insert_text((72, 100), "visible SECRET text", fontsize=12)
a = p.add_text_annot((300, 300), "SECRET annotation to bake")
a.update()
d.set_metadata({"title": "SECRET", "author": "SECRET"})
d.embfile_add("payload.bin", b"SECRET-ATTACHMENT-BODY")
FLAT = d.tobytes()
d.close()

d = pymupdf.open()
d.new_page().insert_text((72, 100), "visible SECRET text", fontsize=12)
d.set_metadata({"title": "SECRET", "author": "SECRET"})
d.embfile_add("payload.bin", b"SECRET-ATTACHMENT-BODY")
ENC = d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw1234",
                owner_pw="pw1234")
d.close()

for ep, blob, data in (("flatten", FLAT, None),
                       ("unlock", ENC, {"password": "pw1234"})):
    r = c.post(f"/api/{ep}", files={"file": ("d.pdf", blob, "application/pdf")},
               data=data)
    chk(f"{ep} runs on a document that suits it", r.status_code == 200,
        f"{r.status_code} {detail(r)[:50]}")
    if r.status_code != 200:
        continue
    dd = pymupdf.open(stream=r.content, filetype="pdf")
    if dd.needs_pass:
        dd.authenticate("pw1234")
    meta = any("SECRET" in str(v) for v in (dd.metadata or {}).values())
    emb = dd.embfile_count()
    dd.close()
    chk(f"{ep}: no metadata, no attachment", not meta and emb == 0,
        f"meta={meta} embedded={emb}")
    chk(f"{ep}: attachment body is gone from the bytes",
        b"SECRET-ATTACHMENT-BODY" not in r.content)

print("\nprotect keeps the password but drops the metadata")
r = c.post("/api/protect", files={"file": ("d.pdf", SRC, "application/pdf")},
           data={"new_password": "hunter2"})
chk("protect works", r.status_code == 200, r.status_code)
if r.status_code == 200:
    d = pymupdf.open(stream=r.content, filetype="pdf")
    chk("the result is encrypted", d.needs_pass)
    d.authenticate("hunter2")
    chk("metadata is gone even so",
        not any("SECRET" in str(v) for v in (d.metadata or {}).values()),
        str(d.metadata)[:70])
    chk("attachment is gone even so", d.embfile_count() == 0)
    d.close()

print("\nredaction reaches the mirrors of the page text")
d = pymupdf.open()
p = d.new_page()
p.insert_text((72, 100), "name SECRET here", fontsize=12)
an = p.add_text_annot((300, 300), "note about SECRET")
an.update()
p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 400, 200, 420),
               "uri": "https://example.com/?q=SECRET"})
MIRR = d.tobytes()
d.close()
r = c.post("/api/redact", files={"file": ("d.pdf", MIRR, "application/pdf")},
           data={"words": "SECRET"})
chk("redact runs", r.status_code == 200, detail(r)[:60])
if r.status_code == 200:
    d = pymupdf.open(stream=r.content, filetype="pdf")
    pg = d[0]
    chk("page text is gone", "SECRET" not in pg.get_text(), pg.get_text()[:40])
    chk("the annotation is gone",
        not any("SECRET" in (a.info.get("content", "") or "")
                for a in (pg.annots() or [])))
    chk("the link target is gone",
        not any("SECRET" in (l.get("uri", "") or "") for l in pg.get_links()))
    chk("nothing left in the raw bytes", b"SECRET" not in r.content)
    d.close()

print("\nlegitimate notes and links survive tools that are not redaction")
r = c.post("/api/rotate", files={"file": ("d.pdf", MIRR, "application/pdf")},
           data={"angle": "90"})
if r.status_code == 200:
    d = pymupdf.open(stream=r.content, filetype="pdf")
    pg = d[0]
    chk("rotate keeps the annotation", len(list(pg.annots() or [])) == 1)
    chk("rotate keeps the link", len(pg.get_links()) == 1)
    d.close()

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("SECURITY OK")
