"""Blank form values, capped error lists, reverse ranges."""
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


def pdf(n=3):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=12)
    b = d.tobytes()
    d.close()
    return b


B = "----PDFCUY"


def raw(ep, fields, n=3, fname="d.pdf"):
    """Hand-built multipart so an empty value is really on the wire."""
    body = [f'--{B}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{fname}"\r\nContent-Type: application/pdf\r\n\r\n'
            .encode() + pdf(n) + b"\r\n"]
    for k, v in fields.items():
        body.append(f'--{B}\r\nContent-Disposition: form-data; name="{k}"'
                    f"\r\n\r\n{v}\r\n".encode())
    body.append(f"--{B}--\r\n".encode())
    r = c.post(f"/api/{ep}", content=b"".join(body),
               headers={"Content-Type": f"multipart/form-data; boundary={B}"})
    det = ""
    if r.status_code != 200:
        try:
            det = r.json().get("detail", "")
        except Exception:
            det = r.text[:90]
    return r, det


print("a blank value no longer becomes the default")
for ep, fields, who in (
    ("compress", {"level": ""}, "level"),
    ("split", {"mode": ""}, "mode"),
    ("page-numbers", {"position": ""}, "position"),
    ("page-numbers", {"fmt": ""}, "fmt"),
    ("watermark", {"place": ""}, "place"),
    ("watermark", {"tile": ""}, "tile"),
    ("rotate", {"angle": ""}, "angle"),
    ("pdf-to-images", {"dpi": ""}, "dpi"),
    ("pdf-to-images", {"fmt": ""}, "fmt"),
    ("office-to-pdf", {"combine": ""}, "combine"),
    ("redact", {"match_case": ""}, "match_case"),
    ("sign", {"corner": ""}, "corner"),
    ("crop", {"top": ""}, "top"),
    ("html-to-pdf", {"size": ""}, "size"),
):
    r, det = raw(ep, fields)
    chk(f"{ep} rejects {who}=''", r.status_code == 400, f"{r.status_code} {det[:46]}")

r, det = raw("compress", {"level": "   "})
chk("whitespace counts as blank", r.status_code == 400, det[:50])
chk("the message names the field", "level" in det, det[:60])
chk("the message says what to do instead", "leave the field out" in det, det[-44:])

print("\nfields where blank legitimately means 'unset'")
for ep, fields, who in (
    ("compress", {"password": ""}, "password"),
    ("extract-text", {"pages": ""}, "pages"),
    ("organize", {"remove": ""}, "remove"),
):
    r, det = raw(ep, fields)
    chk(f"{ep} still accepts {who}=''", r.status_code == 200,
        f"{r.status_code} {det[:40]}")

# Watermark text is not on that list: it defaults to CONFIDENTIAL, so a blank
# value used to stamp a word the caller never typed, while a single space
# errored. Both now report the same thing.
r, det = raw("watermark", {"text": ""})
chk("blank watermark text is reported", r.status_code == 400, f"{r.status_code} {det[:46]}")
r2, det2 = raw("watermark", {"text": "   "})
chk("spaces and empty behave the same", r2.status_code == r.status_code,
    f"{r.status_code} vs {r2.status_code}")
r3, _ = raw("watermark", {})
chk("omitting text still uses the default", r3.status_code == 200, r3.status_code)

print("\nomitting a field entirely still uses its default")
for ep in ("compress", "rotate", "pdf-to-images"):
    r, det = raw(ep, {})
    chk(f"{ep} works with no settings at all", r.status_code == 200,
        f"{r.status_code} {det[:40]}")
r, _ = raw("compress", {"level": "high"})
chk("a real value still works", r.status_code == 200)

print("\nerror messages stay a sane size")
spec = ",".join(str(i) for i in range(1, 4000))
r, det = raw("extract-text", {"pages": spec})
chk("huge bad spec is rejected", r.status_code == 400, r.status_code)
chk("error body stays small", len(r.content) < 400, f"{len(r.content)} bytes")
chk("error names a few pages then counts the rest", "and " in det and "more" in det,
    det[:95])

print("\nreverse ranges survive, impossible ones do not")
r, det = raw("extract-pages", {"pages": "5-2"}, n=10)
chk("5-2 on a 10-page file works", r.status_code == 200, f"{r.status_code} {det[:40]}")
if r.status_code == 200:
    d = pymupdf.open(stream=r.content, filetype="pdf")
    got = [p.get_text().strip() for p in d]
    chk("pages come back in reverse order",
        got == ["Page 5", "Page 4", "Page 3", "Page 2"], str(got))
    d.close()
r, det = raw("extract-pages", {"pages": "9-2"}, n=3)
# '9-2' and '2-99' describe the same span, so they must behave the same way:
# both overlap the document and both clamp. Refusing one while clamping the
# other would be arbitrary.
chk("9-2 on a 3-page file clamps like 2-99 does", r.status_code == 200,
    f"{r.status_code} {det[:40]}")
if r.status_code == 200:
    d = pymupdf.open(stream=r.content, filetype="pdf")
    got = [p.get_text().strip() for p in d]
    chk("clamped reverse range keeps its direction", got == ["Page 3", "Page 2"],
        str(got))
    d.close()
r, det = raw("extract-pages", {"pages": "9-7"}, n=3)
chk("a reverse range fully past the end is refused", r.status_code == 400,
    det[:50])
r, det = raw("extract-pages", {"pages": "3-1"}, n=3)
chk("3-1 on a 3-page file works", r.status_code == 200, f"{r.status_code} {det[:40]}")
r, det = raw("extract-pages", {"pages": "2-99"}, n=3)
chk("2-99 clamps rather than failing", r.status_code == 200,
    f"{r.status_code} {det[:40]}")

print("\nthe guard did not break file reading")
r, det = raw("compress", {"level": "high"}, n=12)
chk("a larger file still processes", r.status_code == 200 and len(r.content) > 500,
    f"{len(r.content)} bytes out")
r, det = raw("extract-text", {"pages": "1-3"}, n=5)
chk("text extraction still sees the pages",
    r.status_code == 200 and b"Page 3" in r.content, r.content[:40])

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("BLANKS OK")
