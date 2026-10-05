"""Drive the new tools through the real browser UI."""
import os
import shutil
import tempfile

import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright

TMP = tempfile.mkdtemp(prefix="nf_")
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
for i in range(5):
    p = d.new_page()
    p.insert_text((72, 90), f"Chapter {i + 1}", fontsize=22)
    p.insert_text((72, 140), "Body line holding ACCOUNT-7781 inside.", fontsize=11)
PDF = os.path.join(TMP, "report.pdf")
d.save(PDF)
d.close()

SIG = os.path.join(TMP, "signature.png")
Image.new("RGB", (320, 110), (20, 30, 110)).save(SIG)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1360, "height": 1000}, accept_downloads=True)
    errs = []
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))

    def goto(tool):
        pg.goto(f"http://127.0.0.1:8000/#{tool}", wait_until="networkidle")
        pg.wait_for_timeout(500)

    def set_opt(key, value):
        pg.evaluate("""([k, v]) => {
          const el = document.getElementById('o_' + k);
          el.value = v;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        }""", [key, value])

    def run_and_get(tool, files=PDF, opts=None, extra=None, advance=True):
        goto(tool)
        if files:
            pg.set_input_files("#picker", files)
            pg.wait_for_timeout(450)
        if advance and pg.locator("#advbtn").is_visible():
            pg.click("#advbtn")
            pg.wait_for_timeout(200)
        for k, v in (opts or {}).items():
            set_opt(k, v)
        if extra:
            pg.set_input_files("#xpick", extra)
            pg.wait_for_timeout(400)
        with pg.expect_download(timeout=60000) as dl:
            pg.click("#go")
        path = dl.value.path()
        return dl.value.suggested_filename, open(path, "rb").read()

    print("remove pages")
    name, data = run_and_get("remove-pages", opts={"pages": "2,4"})
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("3 pages remain", x.page_count == 3, f"{x.page_count} pages, {name}")
    x.close()

    print("extract pages")
    name, data = run_and_get("extract-pages", opts={"pages": "4,1"})
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("order respected", x.page_count == 2 and "Chapter 4" in x[0].get_text(),
        repr(x[0].get_text()[:12]))
    x.close()

    print("page numbers")
    name, data = run_and_get("page-numbers", opts={"fmt": "page_n"})
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("number stamped", "Page 1" in x[0].get_text(), repr(x[0].get_text()[-12:]))
    x.close()

    print("crop")
    goto("crop")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    set_opt("top", "15")
    with pg.expect_download(timeout=60000) as dl:
        pg.click("#go")
    data = open(dl.value.path(), "rb").read()
    x = pymupdf.open(stream=data, filetype="pdf")
    src = pymupdf.open(PDF)
    chk("page trimmed 15 percent", abs(x[0].rect.height - src[0].rect.height * 0.85) < 2,
        f"{src[0].rect.height:.0f} -> {x[0].rect.height:.0f}")
    src.close()
    x.close()

    print("repair")
    broken = bytearray(open(PDF, "rb").read())
    i = broken.rfind(b"startxref")
    broken[i:i + 9] = b"startxr3f"
    BAD = os.path.join(TMP, "damaged.pdf")
    open(BAD, "wb").write(bytes(broken))
    name, data = run_and_get("repair", files=BAD)
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("all pages recovered", x.page_count == 5, f"{x.page_count} pages")
    x.close()

    print("redact")
    name, data = run_and_get("redact", opts={"words": "ACCOUNT-7781"})
    x = pymupdf.open(stream=data, filetype="pdf")
    left = "".join(p.get_text() for p in x)
    chk("secret text destroyed", "ACCOUNT-7781" not in left,
        "unrecoverable" if "ACCOUNT-7781" not in left else "STILL THERE")
    chk("rest of the text kept", "Chapter 1" in left)
    x.close()

    print("sign")
    name, data = run_and_get("sign", extra=SIG)
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("signature on last page", len(x[x.page_count - 1].get_images()) == 1)
    x.close()
    goto("sign")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    chk("run blocked until signature added", pg.is_disabled("#go"),
        pg.inner_text("#gotxt"))
    chk("button says what is missing",
        "signature" in pg.inner_text("#gotxt").lower(), pg.inner_text("#gotxt"))

    print("html to pdf")
    goto("html-to-pdf")
    chk("settings visible with no file", not pg.is_hidden("#optpanel"))
    set_opt("html", "<h1>Quote</h1><p>Total 240</p>")
    chk("run enabled without a file", not pg.is_disabled("#go"), pg.inner_text("#gotxt"))
    with pg.expect_download(timeout=60000) as dl:
        pg.click("#go")
    data = open(dl.value.path(), "rb").read()
    x = pymupdf.open(stream=data, filetype="pdf")
    chk("html rendered", "Quote" in x[0].get_text(), repr(x[0].get_text()[:16]))
    x.close()

    print("pdf to markdown")
    name, data = run_and_get("pdf-to-markdown")
    md = data.decode()
    chk("markdown heading", "# Chapter 1" in md, repr(md[:18]))
    chk("named .md", name.endswith(".md"), name)

    print("compress through the ui")
    import io as _io
    import random
    random.seed(3)
    im = Image.new("RGB", (1600, 1150))
    px = im.load()
    for y in range(0, 1150, 4):
        for x2 in range(0, 1600, 4):
            c = (random.randint(70, 200), random.randint(70, 200), random.randint(90, 210))
            for dy in range(4):
                for dx in range(4):
                    if x2 + dx < 1600 and y + dy < 1150:
                        px[x2 + dx, y + dy] = c
    jb = _io.BytesIO()
    im.save(jb, "JPEG", quality=95)
    scan = pymupdf.open()
    for _ in range(3):
        p = scan.new_page()
        p.insert_image(p.rect, stream=jb.getvalue())
        p.insert_text((60, 60), "Scanned invoice", fontsize=13)
    SCAN = os.path.join(TMP, "scan.pdf")
    scan.save(SCAN)
    scan.close()
    before = os.path.getsize(SCAN)
    name, data = run_and_get("compress", files=SCAN, advance=False)
    pct = 100 - len(data) * 100 / before
    chk("scan really shrinks", pct > 40,
        f"{before // 1024}KB -> {len(data) // 1024}KB ({pct:+.0f}%)")

    print("validation still guards the new tools")
    goto("remove-pages")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    pg.click("#go")
    pg.wait_for_timeout(600)
    chk("required pages field blocks run", pg.is_visible(".note.e"),
        pg.inner_text(".note.e")[:60] if pg.is_visible(".note.e") else "no error")
    goto("crop")
    pg.set_input_files("#picker", PDF)
    pg.wait_for_timeout(400)
    set_opt("top", "90")
    pg.click("#go")
    pg.wait_for_timeout(600)
    chk("out-of-range crop caught client-side", pg.is_visible(".note.e"),
        pg.inner_text(".note.e")[:60] if pg.is_visible(".note.e") else "no error")

    chk("zero console errors", not errs, errs[:2] or "clean")
    csp = [e for e in errs if "Content Security Policy" in e]
    chk("zero CSP violations", not csp, f"{len(csp)} blocked" if csp else "none")
    b.close()

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{ok} passed, {fail} failed")
assert fail == 0
print("NEW UI OK")
