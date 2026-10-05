"""A domain is only worth owning if the site can be found and shared.

The landing page should be indexable; tool output never should. These two must
not be confused, because /api/ responses are somebody's documents.
"""
import io
import os
import re

os.environ.pop("PDFCUY_MAX_MB", None)

import pymupdf  # noqa: E402
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
html = io.open("static/index.html", encoding="utf-8").read()

print("the landing page can be indexed")
chk("no noindex meta tag", "noindex" not in html.lower(),
    next((l.strip() for l in html.splitlines()
          if "noindex" in l.lower()), ""))
r = c.get("/")
tag = r.headers.get("X-Robots-Tag", "")
chk("no noindex header on the page", "noindex" not in tag, tag or "absent")
chk("still no-store", r.headers.get("Cache-Control") == "no-store",
    r.headers.get("Cache-Control"))

print("\ntool output is never indexed")
d = pymupdf.open()
d.new_page()
pdf = d.tobytes()
d.close()
r = c.post("/api/compress", files={"file": ("a.pdf", pdf, "application/pdf")})
tag = r.headers.get("X-Robots-Tag", "")
chk("download carries noindex", "noindex" in tag, tag or "MISSING")
chk("and nofollow", "nofollow" in tag, tag)
chk("and noarchive", "noarchive" in tag, tag)
r = c.post("/api/info", files={"file": ("a.pdf", pdf, "application/pdf")})
chk("info endpoint too", "noindex" in r.headers.get("X-Robots-Tag", ""))

print("\nrobots.txt exists and says the same thing")
r = c.get("/robots.txt")
chk("served", r.status_code == 200, r.status_code)
body = r.text
chk("plain text", r.headers["content-type"].startswith("text/plain"),
    r.headers["content-type"])
chk("api disallowed", "Disallow: /api/" in body, repr(body))
chk("root allowed", "Allow: /$" in body, repr(body))

print("\nshare cards carry no hardcoded host")
chk("og:title present", 'property="og:title"' in html)
chk("og:description present", 'property="og:description"' in html)
chk("twitter card present", 'name="twitter:card"' in html)
# An absolute og:url survives exactly until the domain changes, which is the
# one thing a new domain guarantees.
abs_url = re.findall(r'(?:og:url|og:image)"[^>]*content="(https?://[^"]+)"',
                     html)
chk("no absolute og:url or og:image", not abs_url, abs_url)
chk("no vercel.app reference anywhere",
    "vercel.app" not in html, "found one")

print("\nnothing else regressed")
r = c.get("/")
low = {k.lower(): v for k, v in r.headers.items()}
chk("csp intact", "default-src 'none'" in low.get(
    "content-security-policy", ""))
chk("referrer policy intact", low.get("referrer-policy") == "no-referrer")
chk("frame deny intact", low.get("x-frame-options") == "DENY")
chk("brand still uppercase", "PDFCUY" in r.text and "pdfcuy<" not in r.text)
chk("pure ascii", all(ord(ch) < 128 for ch in html))

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("SEO OK")
