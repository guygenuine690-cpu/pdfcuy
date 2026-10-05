"""A tool the server cannot run must not be reachable anywhere in the UI.

Serves the real static files but answers /api/engines with pdf2docx: false, so
this exercises the hide path without uninstalling anything.
"""
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8213
ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_GET(self):
        if self.path.startswith("/api/engines"):
            body = json.dumps({
                "libreoffice": False, "builtin": True,
                "pdf2docx": False,          # the case under test
                "maxMb": 4, "maxPages": 1500, "maxFiles": 50,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/":
            # index.html links to /static/..., so the document root has to be
            # the repository root, not the static directory.
            self.path = "/static/index.html"
        return super().do_GET()

    def log_message(self, *a):
        pass


srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base, wait_until="networkidle")

    print("the missing tool is gone from the library")
    chk("no pdf-to-docx card",
        pg.locator("[data-k='pdf-to-docx']").count() == 0,
        pg.locator("[data-k='pdf-to-docx']").count())
    chk("other convert cards still there",
        pg.locator("[data-k='pdf-to-xlsx']").count() == 1)
    chk("no footer link to it",
        pg.locator("a[data-open='pdf-to-docx']").count() == 0)
    chk("no stale 'PDF to Word' text anywhere",
        "PDF to Word" not in pg.inner_text("body"))

    print("\nthe section count matches what is shown")
    sec = pg.locator("#cat-convert")
    shown = sec.locator(".tool:not([hidden])").count()
    badge = sec.locator(".cnt").inner_text()
    chk("badge agrees with the cards", badge.startswith(str(shown)),
        f"badge {badge!r} vs {shown} cards")

    print("\nsearch cannot surface it")
    pg.fill("#q", "word")
    pg.wait_for_timeout(250)
    chk("searching 'word' does not reveal it",
        pg.locator("[data-k='pdf-to-docx']").count() == 0)
    pg.fill("#q", "")
    pg.wait_for_timeout(200)

    print("\ninteraction still works after the rebuild")
    pg.click("[data-k='merge']")
    pg.wait_for_timeout(350)
    chk("a card still opens its workspace",
        pg.locator("#workspace").is_visible())
    chk("the opened tool is the right one",
        pg.inner_text("#wtitle").strip().lower().startswith("merge"),
        pg.inner_text("#wtitle"))
    pg.go_back()
    pg.wait_for_timeout(300)
    chk("back returns to the library", pg.locator("#sections").is_visible())

    print("\na deep link to the hidden tool does not open it")
    pg.goto(f"{base}/#pdf-to-docx", wait_until="networkidle")
    pg.wait_for_timeout(400)
    chk("library shown instead of a dead workspace",
        pg.locator("#sections").is_visible())
    title = pg.locator("#wtitle").inner_text() if \
        pg.locator("#wtitle").count() else ""
    chk("workspace did not load the hidden tool",
        "word" not in title.lower(), repr(title))

    print("\nthe advertised size limit is the server's")
    chk("footer figure updated", pg.inner_text("#fmax").strip() == "4 MB",
        pg.inner_text("#fmax"))

    chk("no page errors", not errs, "; ".join(errs[:2]))
    b.close()

srv.shutdown()
print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("DEGRADE OK")
