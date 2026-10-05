"""Nothing in the shipped app may assume where it is running.

The worry is real: a site that works on localhost and breaks on a domain
usually has an absolute URL baked in somewhere.
"""
import io
import os
import re

os.environ["VERCEL"] = "1"

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

print("the client never names a host")
js = io.open("static/main.js", encoding="utf-8").read()
html = io.open("static/index.html", encoding="utf-8").read()
calls = re.findall(r"fetch\(\s*['\"`]([^'\"`]+)", js)
chk("every fetch is a relative path",
    all(u.startswith("/") for u in calls), calls)
bad = [u for u in re.findall(r"['\"`](https?://[^'\"`]+)", js)
       if "w3.org" not in u]
chk("no absolute URL in the script", not bad, bad)
chk("no localhost in the script",
    "localhost" not in js and "127.0.0.1" not in js)
chk("no localhost in the page",
    "localhost" not in html and "127.0.0.1" not in html)

print("\nthe server binding is dev-only")
src = io.open("app.py", encoding="utf-8").read()
tail = src.split('if __name__ == "__main__":', 1)
chk("app.py has a dev entry block", len(tail) == 2)
chk("127.0.0.1 appears only inside it, or in a comment",
    all("127.0.0.1" not in ln or ln.lstrip().startswith("#")
        for ln in tail[0].splitlines()),
    [ln.strip() for ln in tail[0].splitlines()
     if "127.0.0.1" in ln and not ln.lstrip().startswith("#")])

print("\nit answers correctly under any host header")
for host in ["pdfcuy.vercel.app", "pdfcuy.com", "docs.example.co.uk",
             "a-very-long-subdomain.pdfcuy.io"]:
    r = c.get("/", headers={"Host": host})
    body_ok = r.status_code == 200 and b"PDFCUY" in r.content
    leaked = host.encode() not in r.content
    chk(f"{host}", body_ok and leaked,
        "" if body_ok and leaked else f"status {r.status_code}")

print("\nredirects and links stay relative")
r = c.get("/robots.txt", headers={"Host": "pdfcuy.com"})
chk("robots.txt names no host",
    "http" not in r.text, repr(r.text))
# A Location header pointing at the wrong origin is the classic way a moved
# site sends users back to the old one.
for path in ["/", "/static/app.css", "/robots.txt"]:
    r = c.get(path, headers={"Host": "pdfcuy.com"})
    loc = r.headers.get("location", "")
    chk(f"no absolute redirect from {path}",
        not loc.startswith("http"), loc)

print("\nthe API works the same way")
r = c.get("/api/engines", headers={"Host": "pdfcuy.com"})
chk("engines reachable", r.status_code == 200, r.status_code)
chk("engines leaks no host", "pdfcuy.com" not in r.text, r.text[:60])

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("HOST OK")
