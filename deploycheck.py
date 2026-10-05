"""Does the Vercel entry point import and serve the same app?"""
import io
import json
import os
import sys

# Vercel sets PDFCUY_MAX_MB in the dashboard; mimic that here.
os.environ["PDFCUY_MAX_MB"] = "4"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
import importlib.util as u  # noqa: E402

spec = u.spec_from_file_location("vercel_entry", os.path.join("api", "index.py"))
mod = u.module_from_spec(spec)
spec.loader.exec_module(mod)

from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(mod.app)
ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


print("the entry point exposes the real app")
chk("app object found", hasattr(mod, "app"))
r = c.get("/")
chk("index served", r.status_code == 200 and b"PDFCUY" in r.content, r.status_code)
chk("static css served", c.get("/static/app.css").status_code == 200)
chk("no server banner", "server" not in {k.lower() for k in r.headers})
chk("csp present", "content-security-policy" in
    {k.lower() for k in r.headers})

e = c.get("/api/engines").json()
chk("limit comes from the environment", e["maxMb"] == 4, json.dumps(e))

print("\nthe tool list is complete")
src = io.open("app.py", encoding="utf-8").read()
eps = sorted(set(__import__("re").findall(r'@app\.post\("(/api/[a-z-]+)"\)', src)))
chk("27 tool endpoints plus info", len(eps) == 28, f"{len(eps)} found")

print("\npdf-to-docx degrades honestly when the converter is absent")
try:
    import pdf2docx  # noqa: F401
    have = True
except ImportError:
    have = False
print(f"  pdf2docx installed locally: {have}")
req = io.open(os.path.join("api", "requirements.txt"), encoding="utf-8").read()
chk("pdf2docx excluded from the deployment bundle", "pdf2docx" not in req)
chk("the endpoint catches the missing import", "except ImportError" in src)
chk("it answers 501, not 500", 'HTTPException(\n            501,' in src
    or "501," in src)
chk("it names an alternative", "PDF to Markdown" in src)

print("\nconfiguration files are consistent")
vj = json.loads(io.open("vercel.json", encoding="utf-8").read())
chk("function points at the entry file", "api/index.py" in vj["functions"])
chk("all paths rewritten to it",
    vj["rewrites"][0]["destination"] == "/api/index.py")
chk("python runtime pinned",
    vj["functions"]["api/index.py"]["runtime"].startswith("python"))
entry = io.open(os.path.join("api", "index.py"), encoding="utf-8").read()
chk("entry adds the parent directory to the path", "sys.path.insert" in entry)

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("DEPLOY OK")
