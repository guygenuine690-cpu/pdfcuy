"""HSTS must follow the connection, not the hope of one."""
import os

os.environ.pop("PDFCUY_MAX_MB", None)

from fastapi.testclient import TestClient  # noqa: E402

import app as A  # noqa: E402

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


c = TestClient(A.app)
H = "strict-transport-security"

print("plain http gets no HSTS")
r = c.get("/")
chk("absent over http", H not in {k.lower() for k in r.headers},
    r.headers.get(H, ""))

print("\nhttps gets it")
r = c.get("https://testserver/")
v = r.headers.get(H, "")
chk("present over https", bool(v), v or "missing")
chk("two years", "max-age=63072000" in v, v)
chk("covers subdomains", "includeSubDomains" in v, v)
# preload is a one-way door: browsers ship the entry and removal takes months.
# That is a decision for whoever owns the domain, not a library default.
chk("does not claim preload", "preload" not in v, v)

print("\na terminating proxy is believed")
r = c.get("/", headers={"x-forwarded-proto": "https"})
chk("set behind a TLS proxy", H in {k.lower() for k in r.headers},
    r.headers.get(H, "missing"))
r = c.get("/", headers={"x-forwarded-proto": "https, http"})
chk("reads the first hop of a chain", H in {k.lower() for k in r.headers})
r = c.get("/", headers={"x-forwarded-proto": "http"})
chk("not set when the proxy reports http",
    H not in {k.lower() for k in r.headers}, r.headers.get(H, ""))

print("\nthe rest of the posture is unchanged")
r = c.get("/")
low = {k.lower(): v for k, v in r.headers.items()}
for h, want in [("x-content-type-options", "nosniff"),
                ("x-frame-options", "DENY"),
                ("referrer-policy", "no-referrer"),
                ("cross-origin-opener-policy", "same-origin")]:
    chk(h, low.get(h) == want, low.get(h, "missing"))
chk("csp still strict", "default-src 'none'" in low.get(
    "content-security-policy", ""))
chk("no server banner", "server" not in low)

print("\nit reaches file responses too")
import pymupdf  # noqa: E402

d = pymupdf.open()
d.new_page()
pdf = d.tobytes()
d.close()
r = c.post("https://testserver/api/compress",
           files={"file": ("a.pdf", pdf, "application/pdf")})
chk("download carries HSTS", r.status_code == 200 and H in
    {k.lower() for k in r.headers}, r.status_code)

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("TLS OK")
