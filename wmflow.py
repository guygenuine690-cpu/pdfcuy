"""Watermark logo/tile/angle and Flatten, driven through the real UI."""
import io
import os
import shutil
import tempfile

import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright

TMP = tempfile.mkdtemp(prefix="wm_")
ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


d = pymupdf.open()
for i in range(3):
    p = d.new_page()
    p.insert_text((72, 100), f"Contract page {i + 1}", fontsize=13)
PDF = os.path.join(TMP, "contract.pdf")
d.save(PDF)
d.close()

LOGO = os.path.join(TMP, "logo.png")
Image.new("RGB", (400, 160), (200, 40, 60)).save(LOGO)

fd = pymupdf.open()
pg1 = fd.new_page()
pg1.insert_text((72, 100), "Name:", fontsize=12)
w = pymupdf.Widget()
w.field_name = "who"
w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
w.rect = pymupdf.Rect(130, 86, 320, 106)
w.field_value = "Grace Hopper"
pg1.add_widget(w)
FORM = os.path.join(TMP, "form.pdf")
fd.save(FORM)
fd.close()

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1360, "height": 1000}, accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error"
          and "Failed to load resource" not in m.text
          and errs.append(m.text))

    def goto(tool):
        pg.goto(f"http://127.0.0.1:8000/#{tool}", wait_until="networkidle")
        pg.wait_for_timeout(500)

    def opt(k, v):
        pg.evaluate("""([k, v]) => {
          const el = document.getElementById('o_' + k);
          el.value = v;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        }""", [k, v])

    def seg(k, v):
        pg.click(f"[data-seg='{k}'] button[data-v='{v}']")
        pg.wait_for_timeout(200)

    def grab(expect_ok=True):
        with pg.expect_download(timeout=60000) as dl:
            pg.click("#go")
        return open(dl.value.path(), "rb").read()

    print("watermark keeps working with plain text")
    goto("watermark")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    opt("text", "DRAFT COPY")
    data = grab()
    doc = pymupdf.open(stream=data, filetype="pdf")
    chk("text stamped", "DRAFT COPY" in doc[0].get_text(), repr(doc[0].get_text()[:40]))
    doc.close()

    print("diagonal angle")
    goto("watermark")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    opt("text", "SECRET")
    opt("angle", "45")
    data = grab()
    doc = pymupdf.open(stream=data, filetype="pdf")
    chk("diagonal text present", "SECRET" in doc[0].get_text())
    doc.close()

    print("tiling")
    goto("watermark")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    opt("text", "VOID")
    seg("tile", "on")
    data = grab()
    doc = pymupdf.open(stream=data, filetype="pdf")
    n = doc[0].get_text().count("VOID")
    chk("tiled 9 times via the segmented control", n == 9, f"{n} copies")
    doc.close()

    print("logo watermark")
    goto("watermark")
    chk("logo input is shown", pg.is_visible("#extrawrap"))
    chk("logo is marked optional", pg.locator("#extrawrap .rq").count() == 0,
        "no required asterisk")
    chk("logo hint explains the override",
        "instead of the text" in pg.inner_text("#extrawrap").lower(),
        pg.inner_text("#extrawrap")[:60])
    chk("logo size hidden until a logo is added", pg.locator("#o_width").count() == 0)
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    chk("run is allowed without a logo", not pg.is_disabled("#go"),
        pg.inner_text("#gotxt"))
    pg.set_input_files("#xpick", LOGO)
    pg.wait_for_timeout(500)
    chk("chosen logo is listed", "logo.png" in pg.inner_text("#extrawrap"))
    chk("text field hides once a logo is attached",
        pg.locator("#o_text").count() == 0, "no dead setting left on screen")
    chk("logo size appears only with a logo", pg.locator("#o_width").count() == 1)
    opt("width", "35")
    data = grab()
    doc = pymupdf.open(stream=data, filetype="pdf")
    chk("logo embedded on page 1", len(doc[0].get_images()) == 1,
        f"{len(doc[0].get_images())} images")
    chk("default word not also stamped", "CONFIDENTIAL" not in doc[0].get_text(),
        "logo took priority")
    doc.close()

    print("logo can be removed again")
    pg.wait_for_timeout(300)
    goto("watermark")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(300)
    pg.set_input_files("#xpick", LOGO)
    pg.wait_for_timeout(400)
    pg.click("#xrm")
    pg.wait_for_timeout(400)
    chk("remove restores the chooser", pg.locator("#xbtn").count() == 1)
    chk("text field comes back", pg.locator("#o_text").count() == 1)

    print("switching tools forgets the logo")
    goto("watermark")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(300)
    pg.set_input_files("#xpick", LOGO)
    pg.wait_for_timeout(400)
    goto("sign")
    chk("sign starts with no image carried over",
        pg.locator("#xbtn").count() == 1, "chooser shown")

    print("flatten")
    goto("flatten")
    pg.set_input_files("#picker", FORM)
    pg.wait_for_timeout(400)
    data = grab()
    doc = pymupdf.open(stream=data, filetype="pdf")
    chk("widgets gone", sum(1 for q in doc for _ in q.widgets()) == 0)
    chk("typed value kept as real text", "Grace Hopper" in doc[0].get_text(),
        repr(doc[0].get_text()[:40]))
    doc.close()

    print("flatten explains itself on a plain file")
    goto("flatten")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    pg.click("#go")
    pg.wait_for_timeout(1500)
    txt = pg.inner_text(".note.e") if pg.is_visible(".note.e") else ""
    chk("plain PDF gets a clear reason",
        "no form fields or annotations" in txt, txt[:60] or "no error shown")

    print("impossible page is reported, not ignored")
    goto("extract-pages")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    opt("pages", "1,99")
    pg.click("#go")
    pg.wait_for_timeout(1500)
    txt = pg.inner_text(".note.e") if pg.is_visible(".note.e") else ""
    chk("page 99 of a 3-page file is called out", "3 pages" in txt and "99" in txt,
        txt[:60] or "no error shown")

    # The two checks above intentionally provoke 400s, and the browser logs every
    # failed response, so those are filtered out above. A real script fault or a
    # blocked resource still lands here.
    chk("zero script errors", not errs, errs[:2] or "clean")
    csp = [e for e in errs if "Content Security Policy" in e]
    chk("zero CSP violations", not csp, f"{len(csp)} blocked" if csp else "none")
    b.close()

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("WATERMARK UI OK")
