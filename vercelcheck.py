"""The Vercel entry point and config must be valid for the platform.

These are the mistakes that fail a build rather than a test, so they are
asserted here instead of being discovered in a deployment log.
"""
import io
import json
import os
import sys

os.environ["VERCEL"] = "1"            # mimic the platform
os.environ.pop("PDFCUY_MAX_MB", None)
os.environ.pop("PDFCUY_MAX_PAGES", None)

import importlib.util as u  # noqa: E402

spec = u.spec_from_file_location("vercel_entry", os.path.join("api", "index.py"))
mod = u.module_from_spec(spec)
spec.loader.exec_module(mod)

from fastapi.testclient import TestClient  # noqa: E402

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


c = TestClient(mod.app)
vj = json.loads(io.open("vercel.json", encoding="utf-8").read())
fn = vj["functions"]["api/index.py"]
dur = fn["maxDuration"]

print("the platform defaults apply themselves")
e = c.get("/api/engines").json()
chk("size cap drops to 4 MB", e["maxMb"] == 4, json.dumps(e))
chk("page cap drops below the 1500 default", e["maxPages"] < 1500,
    e["maxPages"])

print("\nthe page cap fits inside the function timeout")
# Measured: roughly 35 pages per second of compression on this machine.
# A cap that needs longer than the function may run is a request that is
# accepted and then killed, which is worse than a refusal.
RATE = 35
need = e["maxPages"] / RATE
chk("worst-case work fits in maxDuration", need <= dur,
    f"{e['maxPages']} pages ~= {need:.0f}s vs {dur}s limit")

print("\nconfig has nothing that fails a Hobby build")
chk("duration within the Hobby ceiling", dur <= 60, dur)
chk("no legacy version key", "version" not in vj, vj.get("version"))
chk("no memory override", "memory" not in fn)
chk("no pinned runtime", "runtime" not in fn)
chk("rewrite omits the .py suffix",
    vj["rewrites"][0]["destination"] == "/api/index",
    vj["rewrites"][0]["destination"])
chk("every path routed", vj["rewrites"][0]["source"] == "/(.*)")

print("\nthe entry point still serves the real app")
r = c.get("/")
chk("index served", r.status_code == 200 and b"PDFCUY" in r.content,
    r.status_code)
chk("static served", c.get("/static/app.css").status_code == 200)
chk("robots served", c.get("/robots.txt").status_code == 200)
chk("csp intact", "content-security-policy" in
    {k.lower() for k in r.headers})
chk("no server banner", "server" not in {k.lower() for k in r.headers})

print("\nthe bundle leaves out what will not fit")
req = io.open(os.path.join("api", "requirements.txt"), encoding="utf-8").read()
chk("pdf2docx excluded from the deployment bundle", "pdf2docx" not in req)
# Locally the converter is installed, so engines reports true here. What must
# hold is that the flag mirrors reality rather than being hardcoded, and that
# the endpoint refuses cleanly when it is absent. degradecheck.py drives the
# false case through a browser.
import importlib.util as iu  # noqa: E402

have = iu.find_spec("pdf2docx") is not None
chk("the flag reflects what is actually installed", e["pdf2docx"] == have,
    f"flag {e['pdf2docx']}, installed {have}")
src = io.open("app.py", encoding="utf-8").read()
chk("a missing converter is caught", "except ImportError" in src)
chk("and answers 501 rather than crashing", "501," in src)

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("VERCEL OK")
