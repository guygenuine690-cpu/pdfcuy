"""Adversarial audit. Acts like a hostile/clumsy user. Reports findings, does not assert.
Run: python audit.py   (needs server running + playwright)"""
import io
import os
import tempfile

import pymupdf
import urllib.request as u
import urllib.error

B = "http://127.0.0.1:8000"
TMP = tempfile.mkdtemp(prefix="audit_")
findings = []


def note(sev, area, what, detail=""):
    findings.append((sev, area, what, detail))
    print(f"  [{sev}] {area}: {what}" + (f"\n        {detail}" if detail else ""))


def post(path, fields, files):
    import uuid
    bnd = "----" + uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, name, data in files:
        body.write(f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                   f"Content-Type: application/octet-stream\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{bnd}--\r\n".encode())
    req = u.Request(B + path, data=body.getvalue(),
                    headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    try:
        r = u.urlopen(req, timeout=120)
        return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def mkpdf(n=2, enc=None):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 100), f"Page {i+1}", fontsize=13)
    buf = d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=enc, user_pw=enc) \
        if enc else d.tobytes()
    d.close()
    return buf


PDF = mkpdf(3)
ENC = mkpdf(2, enc="s3cret")

print("=" * 72)
print("1. MALFORMED AND HOSTILE INPUT")
print("=" * 72)

st, body, _ = post("/api/compress", {}, [("file", "notreally.pdf", b"this is plain text, not a pdf")])
note("PASS" if st >= 400 else "HIGH", "corrupt file",
     f"fake PDF rejected with {st}" if st >= 400 else f"fake PDF accepted ({st})",
     body[:150].decode("utf-8", "replace") if st >= 400 else "")

st, body, _ = post("/api/compress", {}, [("file", "empty.pdf", b"")])
note("PASS" if st >= 400 else "MED", "empty file", f"0-byte rejected with {st}",
     body[:120].decode("utf-8", "replace"))

st, body, _ = post("/api/compress", {}, [("file", "locked.pdf", ENC)])
msg = body[:200].decode("utf-8", "replace")
helpful = "password" in msg.lower()
note("PASS" if st >= 400 and helpful else "MED", "encrypted without password",
     f"status {st}, message mentions password: {helpful}", msg)

st, body, _ = post("/api/compress", {"password": "wrong"}, [("file", "locked.pdf", ENC)])
note("PASS" if st >= 400 else "HIGH", "wrong password", f"status {st}",
     body[:150].decode("utf-8", "replace"))

st, body, hd = post("/api/compress", {"password": "s3cret"}, [("file", "locked.pdf", ENC)])
note("PASS" if st == 200 else "HIGH", "correct password", f"status {st}, {len(body)}B out")

print()
print("=" * 72)
print("2. FILENAME INJECTION AND HEADER SAFETY")
print("=" * 72)

HOSTILE = [
    ("path traversal", "../../../../etc/passwd.pdf"),
    ("windows traversal", "..\\..\\windows\\system32\\evil.pdf"),
    ("crlf header split", 'bad"\r\nX-Injected: yes\r\n\r\n.pdf'),
    ("quote break", 'a"b;filename="other.pdf'),
    ("script tag", "<script>alert(1)</script>.pdf"),
    ("unicode rtl", "doc\u202egnp.pdf"),
    ("very long", "A" * 300 + ".pdf"),
    ("null byte", "ok\x00.pdf"),
]
for label, name in HOSTILE:
    try:
        st, body, hd = post("/api/compress", {}, [("file", name, PDF)])
    except Exception as e:
        note("MED", "filename", f"{label}: request raised {type(e).__name__}", str(e)[:100])
        continue
    cd = hd.get("Content-Disposition", "")
    bad_hdr = "\r" in cd or "\n" in cd or "X-Injected" in str(hd)
    traversal = ".." in cd or "/etc/" in cd or "system32" in cd.lower()
    raw_script = "<script>" in cd
    if st != 200:
        note("INFO", "filename", f"{label}: rejected {st}")
    elif bad_hdr:
        note("CRIT", "filename", f"{label}: header injection possible", cd[:160])
    elif traversal:
        note("HIGH", "filename", f"{label}: traversal survives into header", cd[:160])
    elif raw_script:
        note("MED", "filename", f"{label}: raw script tag in header", cd[:160])
    else:
        note("PASS", "filename", f"{label}: safe", cd[:110])

print()
print("=" * 72)
print("3. PARAMETER ABUSE")
print("=" * 72)

CASES = [
    ("/api/compress", {"level": "ludicrous"}, "unknown enum"),
    ("/api/rotate", {"angle": "45"}, "non-multiple-of-90 angle"),
    ("/api/rotate", {"angle": "-99999"}, "absurd angle"),
    ("/api/pdf-to-images", {"dpi": "99999"}, "dpi overflow"),
    ("/api/pdf-to-images", {"dpi": "-5"}, "negative dpi"),
    ("/api/pdf-to-images", {"dpi": "abc"}, "non-numeric dpi"),
    ("/api/watermark", {"text": "x", "opacity": "99"}, "opacity out of range"),
    ("/api/watermark", {"text": ""}, "empty watermark text"),
    ("/api/compress", {"level": ""}, "blank enum falls back"),
    ("/api/pdf-to-images", {"dpi": ""}, "blank number falls back"),
    ("/api/page-numbers", {"position": ""}, "blank position falls back"),
    ("/api/extract-text", {"pages": "9999"}, "page out of range"),
    ("/api/extract-text", {"pages": "0"}, "page zero"),
    ("/api/extract-text", {"pages": "-3"}, "negative page"),
    ("/api/extract-text", {"pages": "1-"}, "open-ended range"),
    ("/api/extract-text", {"pages": "5-2"}, "reversed range"),
    ("/api/extract-text", {"pages": "a,b,c"}, "garbage page spec"),
    ("/api/extract-text", {"pages": "1," * 5000}, "huge page spec"),
    ("/api/extract-text", {"pages": ",".join(str(i) for i in range(1, 4000))},
     "error amplification"),
    ("/api/split", {"mode": "nonsense"}, "unknown split mode"),
    ("/api/split", {"mode": "extract", "pages": ""}, "extract with no pages"),
    ("/api/protect", {"new_password": ""}, "empty new password"),
    ("/api/protect", {"new_password": "a"}, "1-char password"),
    ("/api/organize", {"pages": "1,1,1,1"}, "duplicate pages"),
    ("/api/organize", {"remove": "1,2,3"}, "remove every page"),
]
for path, fields, label in CASES:
    st, body, _ = post(path, fields, [("file", "in.pdf", PDF)])
    msg = body[:170].decode("utf-8", "replace").replace("\n", " ")
    crashed = st >= 500
    if crashed:
        note("HIGH", "params", f"{label}: server error {st}", msg)
    elif st == 200:
        note("INFO", "params", f"{label}: accepted, {len(body)}B out")
    else:
        note("PASS", "params", f"{label}: {st} with explanation", msg[:120])
    # A rejection is only useful if a human can read it. One bad spec once
    # produced a 23 KB message listing every missing page.
    if st != 200 and len(body) > 600:
        note("MED", "params", f"{label}: error body is {len(body)}B",
             "an error should not be larger than the answer")

print()
print("=" * 72)
print("4. WRONG-SHAPE REQUESTS")
print("=" * 72)

st, body, _ = post("/api/compress", {}, [])
note("PASS" if 400 <= st < 500 else "MED", "missing file", f"status {st}",
     body[:120].decode("utf-8", "replace"))

st, body, _ = post("/api/merge", {}, [("files", "one.pdf", PDF)])
note("PASS" if st >= 400 else "INFO", "merge with a single file", f"status {st}",
     body[:140].decode("utf-8", "replace"))

st, body, _ = post("/api/compress", {}, [("files", "wrongfield.pdf", PDF)])
note("PASS" if 400 <= st < 500 else "MED", "wrong form field name", f"status {st}")

st, body, _ = post("/api/office-to-pdf", {}, [("files", "image.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 60)])
note("PASS" if st >= 400 else "MED", "image sent to office endpoint", f"status {st}",
     body[:140].decode("utf-8", "replace"))

st, body, _ = post("/api/convert", {"to": "../../etc/passwd"}, [("file", "in.pdf", PDF)])
note("PASS" if st >= 400 else "HIGH", "traversal in target format", f"status {st}",
     body[:140].decode("utf-8", "replace"))

st, body, _ = post("/api/convert", {"to": "pdf; rm -rf /"}, [("file", "in.pdf", PDF)])
note("PASS" if st >= 400 else "HIGH", "shell metachars in format", f"status {st}",
     body[:140].decode("utf-8", "replace"))

try:
    r = u.urlopen(u.Request(B + "/api/compress", method="GET"), timeout=20)
    note("MED", "method", f"GET on a POST endpoint returned {r.status}")
except urllib.error.HTTPError as e:
    note("PASS", "method", f"GET on POST endpoint rejected with {e.code}")

try:
    r = u.urlopen(B + "/static/../app.py", timeout=20)
    note("CRIT", "static", f"source readable through traversal: {r.status}")
except urllib.error.HTTPError as e:
    note("PASS", "static", f"traversal into source blocked ({e.code})")

print()
print("=" * 72)
print("5. HEADERS AND PRIVACY POSTURE")
print("=" * 72)

r = u.urlopen(B + "/", timeout=20)
h = {k.lower(): v for k, v in r.headers.items()}
for name, want, sev in [
    ("cache-control", "no-store", "MED"),
    ("x-content-type-options", "nosniff", "MED"),
    ("referrer-policy", None, "LOW"),
    ("content-security-policy", None, "MED"),
    ("x-frame-options", None, "MED"),
    ("permissions-policy", None, "LOW"),
]:
    got = h.get(name)
    if got and (want is None or want in got):
        note("PASS", "header", f"{name}: {got[:70]}")
    else:
        note(sev, "header", f"{name} missing" if not got else f"{name} is {got[:50]}")

note("INFO", "header", f"server banner: {h.get('server', 'absent')}")
# HSTS is deliberately conditional: it is set only when the request arrived
# over TLS, so a plain-HTTP audit run must not see it. Flag the inverse, which
# would mean a developer's own machine gets pinned to a scheme it cannot serve.
if "strict-transport-security" in h:
    note("MED", "header", "HSTS sent over plain HTTP",
         h["strict-transport-security"][:60])
else:
    note("PASS", "header", "HSTS correctly withheld on plain HTTP")
if "set-cookie" in h:
    note("HIGH", "privacy", "server sets a cookie", h["set-cookie"][:90])
else:
    note("PASS", "privacy", "no Set-Cookie on any response")

print()
print("=" * 72)
print("6. RESIDUE ON DISK")
print("=" * 72)

import glob
import time


def temp_snapshot():
    return {p for p in glob.glob(os.path.join(tempfile.gettempdir(), "*"))}


before = temp_snapshot()
MARKER = b"CANARY-DOCUMENT-CONTENT-9F3A"
marked = pymupdf.open()
marked.new_page().insert_text((72, 100), MARKER.decode(), fontsize=13)
MARKED = marked.tobytes()
marked.close()

post("/api/pdf-to-docx", {}, [("file", "resid.pdf", MARKED)])
post("/api/office-to-pdf", {}, [("files", "resid.pdf", MARKED)])
post("/api/compress", {}, [("file", "resid.pdf", MARKED)])

# Give the OS a moment: uvicorn/starlette spool files are unlinked asynchronously.
leaked, holding = [], []
for _ in range(12):
    time.sleep(0.5)
    leaked = [p for p in temp_snapshot() - before if "audit_" not in p]
    if not leaked:
        break

for p in leaked:
    try:
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            with open(p, "rb") as fh:
                if MARKER in fh.read():
                    holding.append(p)
    except OSError:
        pass  # vanished while we looked: that is the good outcome

if holding:
    note("CRIT", "temp files", f"{len(holding)} file(s) still hold document bytes",
         "\n        ".join(holding[:4]))
elif leaked:
    note("INFO", "temp files",
         f"{len(leaked)} unrelated temp entries appeared, none contain document data",
         "\n        ".join(leaked[:3]))
else:
    note("PASS", "temp files", "nothing left behind in temp")

survivors = [p for p in leaked if os.path.exists(p)]
note("PASS" if not survivors else "INFO", "temp cleanup",
     "every temp entry was reclaimed" if not survivors
     else f"{len(survivors)} entries persist (checked clean)")

cwd_junk = [p for p in os.listdir(".") if p.endswith((".pdf", ".docx", ".tmp", ".xlsx"))]
note("PASS" if not cwd_junk else "MED", "working dir",
     "no stray output files" if not cwd_junk else f"found {cwd_junk}")

print()
print("=" * 72)
print("SUMMARY")
print("=" * 72)
order = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3, "INFO": 4, "PASS": 5}
counts = {}
for sev, *_ in findings:
    counts[sev] = counts.get(sev, 0) + 1
for k in sorted(counts, key=lambda s: order.get(s, 9)):
    print(f"  {k:5} {counts[k]}")

issues = [f for f in findings if f[0] in ("CRIT", "HIGH", "MED", "LOW")]
if issues:
    print("\nACTIONABLE:")
    for sev, area, what, _ in sorted(issues, key=lambda f: order[f[0]]):
        print(f"  [{sev}] {area}: {what}")
else:
    print("\nNo actionable findings.")
