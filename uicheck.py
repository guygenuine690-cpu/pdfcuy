"""Asset + a11y + design-system audit. Needs server running: python uicheck.py"""
import re
import urllib.request as u

B = "http://127.0.0.1:8000"
ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    extra = str(extra).encode("ascii", "replace").decode()
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")


def get(path):
    r = u.urlopen(B + path, timeout=30)
    return r, r.read().decode("utf-8", "replace")


r, html = get("/")
chk("index 200", r.status == 200, f"{len(html)}B")
chk("no-store header", "no-store" in (r.headers.get("Cache-Control") or ""))

A = {}
for path in ("/static/app.css", "/static/work.css", "/static/main.js",
             "/static/icons.js", "/static/tools.js", "/static/brands.js"):
    try:
        rr, body = get(path)
        A[path] = body
        chk(f"{path} served", rr.status == 200, f"{len(body)}B")
    except Exception as e:
        chk(f"{path} served", False, e)

css = A.get("/static/app.css", "") + A.get("/static/work.css", "")
js = A.get("/static/main.js", "")
tools = A.get("/static/tools.js", "")
brands = A.get("/static/brands.js", "")
blob = html + "".join(A.values())

print("no emoji, no icon fonts")
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d\u2190-\u21ff\u2b05-\u2b07]")
hits = sorted({c for c in blob if EMOJI.match(c)})
chk("zero emoji in all assets", not hits, [hex(ord(c)) for c in hits][:10])
chk("icons are inline svg", 'viewBox="0 0 24 24"' in A.get("/static/icons.js", ""))
chk("no external font or cdn request",
    "fonts.googleapis" not in blob and "cdn." not in blob and "//unpkg" not in blob)
chk("no third-party script tag", html.count("<script") == 1, html.count("<script"))
chk("no inline style attribute in markup", 'style="' not in html,
    "strict CSP blocks inline styles")
chk("no inline style written by js",
    ".style." not in js and "style.setProperty" not in js,
    "category hues use .k1-.k4 classes")
chk("category hue classes exist", all(f".k{i}{{" in css for i in (1, 2, 3, 4)))

print("english only")
ID_WORDS = ("halaman", "berkas", "tidak ", "kosong", "gagal", "butuh", "pilih",
            "semua ", "dengan ", "untuk ", "alat ", "ukuran", "konversi", "sandi")
found = sorted({w.strip() for w in ID_WORDS if w in blob.lower()})
chk("no mixed-language copy", not found, found or "clean")
chk("html lang=en", 'lang="en"' in html)

print("tool-first information architecture")
chk("library view present", 'id="library"' in html)
chk("workspace starts hidden", 'id="workspace" hidden' in html)
chk("grid is built from data", "buildLibrary" in js and "toolCard" in js)
chk("4 categories defined", tools.count("{ id: '") == 4, tools.count("{ id: '"))
chk("category nav + scroll-spy", 'id="tnav"' in html and "IntersectionObserver" in js)
chk("search present", 'id="q"' in html and "filter(" in js)
chk("deep links via hash", "history.pushState" in js and "popstate" in js)
chk("breadcrumb back path", 'id="back"' in html and "goLibrary" in js)
chk("format logos per tool", "from:" in tools and "to:" in tools)
chk("featured cards span 2", ".tool.feat{grid-column:span 2}" in css)
chk("progressive options", "adv: 1" in tools and "advbtn" in js)
chk("segmented controls", "seg: 1" in tools and ".seg button" in css)
chk("search covers synonyms", tools.count("kw: '") >= 15, f"{tools.count(chr(107)+chr(119)+': ')} tools tagged")
for word in ("smaller", "combine", "encrypt", "reorder", "spreadsheet", "stamp"):
    chk(f"synonym '{word}' indexed", word in tools)
chk("client validates number ranges", "must be between ${o.min}" in js)

print("brand logos")
chk("logo module exports FMT", "export const FMT" in brands)
chk("gradient ids namespaced", "'fmtg'" in brands and "'fmth'" in brands)
chk("ids unique per render", "++uid" in brands and "get logo()" in brands)
for fmt in ("pdf", "word", "excel", "ppt", "jpg", "txt", "csv", "zip", "any"):
    chk(f"logo: {fmt}", f"{fmt}: {{" in brands)

print("design tokens")
for tok in ("--s1:", "--s9:", "--t1:", "--t8:", "--rc:", "--rf:",
            "--e1:", "--e4:", "--ease:", "--sans:", "--mono:", "--wrap:"):
    chk(f"token {tok}", tok in css)
chk("4 category hues", all(f"--c{i}:" in css for i in (1, 2, 3, 4)))
chk("each hue has a soft pair", all(f"--c{i}s:" in css for i in (1, 2, 3, 4)))
chk("dark theme block", '[data-theme="dark"]' in css)
chk("bento radius 16-24px", "--rc:20px" in css and "--rt:16px" in css)
chk("hover lift per skill spec", "translateY(-4px)" in css)
chk("reduced motion honored", "prefers-reduced-motion" in css)
chk("backdrop-filter has fallback", "@supports not (backdrop-filter" in css)

print("responsive")
for bp in ("1080px", "980px", "860px", "620px", "540px"):
    chk(f"breakpoint {bp}", f"max-width:{bp}" in css.replace(" ", ""))
chk("grid reflows 4-3-2-1", css.count("grid-template-columns:repeat(") >= 3)

print("a11y")
chk("aria-live status region", 'aria-live="polite"' in html)
chk("sr-only class", ".sr{" in css)
chk("global focus-visible", ":focus-visible{outline" in css.replace(" ", ""))
chk("icons aria-hidden", html.count('aria-hidden="true"') >= 10, html.count('aria-hidden="true"'))
chk("buttons typed", html.count('type="button"') >= 6)
chk("labelled regions", html.count("aria-label") + html.count("aria-labelledby") >= 7)
chk("inputs have labels", 'class="lb" for=' in js)
chk("segmented uses aria-pressed", 'aria-pressed' in js)
chk("expandable uses aria-expanded", 'aria-expanded' in html and 'aria-expanded' in js)
chk("nav landmarks", html.count("<nav") >= 2)

print("ux states")
for state, needle in [("loading", "spin"), ("progress bar", "$('bar')"),
                      ("success", "'s')"), ("error", "'e', true)"), ("warning", "'w' : 'i'"),
                      ("empty search", "No tool matches that"),
                      ("error recovery", "Try again"),
                      ("wrong type guard", "is not one."),
                      ("oversize guard", "over the ${MAX_MB} MB limit"),
                      ("min files guard", "Add ${need - n} more"),
                      ("busy guard", "if (busy ||")]:
    chk(f"state: {state}", needle in js, "" if needle in js else needle)
chk("xss escaped", "replace(/[&<>\"']/g" in js)
# The client no longer holds its own copy of the limit: it starts at the
# documented default and takes the real figure from /api/engines, so the UI can
# never advertise a cap the server will refuse.
chk("client size cap", "let MAX = MAX_MB * 1024 * 1024" in js)
chk("cap is corrected from the server", "e.maxMb" in js)
chk("footer figure is addressable", 'id="fmax"' in html)
chk("theme persisted", "localStorage" in js)
chk("escape key handled", "'Escape'" in js)
chk("slash focuses search", "e.key === '/'" in js)
chk("blob url revoked", "revokeObjectURL" in js)

print("endpoint parity")
ids = set(re.findall(r"^\s{2}'?([a-z][a-z0-9-]+)'?:\s*\{", tools, re.M))
api = set(re.findall(r'@app\.post\("/api/([a-z-]+)"', open("app.py", encoding="utf-8").read()))
api -= {"info", "engines"}
chk("every tool maps to an endpoint", ids <= api, sorted(ids - api) or "all mapped")
chk("every endpoint is exposed", api <= ids, sorted(api - ids) or "all exposed")
chk("27 tools", len(ids) == 27, len(ids))
for want in ("redact", "sign", "crop", "repair", "page-numbers", "flatten",
             "remove-pages", "extract-pages", "html-to-pdf", "pdf-to-markdown"):
    chk(f"{want} shipped", want in ids)
chk("textarea control supported", "textarea" in js and "textarea{" in css)
chk("second file input supported", "EXTRA_INPUT" in tools and "drawExtra" in js)
chk("file-optional tools supported", "FILE_OPTIONAL" in tools and "FILE_OPTIONAL" in js)
chk("optional second file supported", "optional: 1" in tools and "xs.optional" in js)
chk("watermark takes a logo", "watermark: {" in tools.split("EXTRA_INPUT")[1][:400])
chk("watermark can tile and rotate",
    "'tile'" in tools and "'angle'" in tools and "'place'" in tools)

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("UI OK")
