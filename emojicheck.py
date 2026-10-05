"""Hard emoji/pictograph ban across every shipped byte, including rendered DOM text."""
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).parent
SHIPPED = ["app.py", "office.py", "README.md", "requirements.txt"] + [
    f"static/{p.name}" for p in sorted((ROOT / "static").iterdir()) if p.is_file()
]

# Any codepoint that is a pictograph, dingbat, emoji presentation, or symbol-other.
BAD_BLOCKS = [
    (0x1F000, 0x1FAFF),  # emoji, pictographs, symbols
    (0x2600, 0x27BF),    # misc symbols + dingbats
    (0x2B00, 0x2BFF),    # arrows/misc
    (0xFE00, 0xFE0F),    # variation selectors
    (0x1F1E6, 0x1F1FF),  # flags
    (0x2190, 0x21FF),    # arrows
    (0x2300, 0x23FF),    # technical (includes hourglass, watch)
]
# No allowlist. The project is pure ASCII on purpose: box-drawing characters
# and typographic dashes are category So/Pd, the same class as emoji, and a
# reviewer reading raw bytes cannot tell a "decorative" symbol from a
# pictograph. Keeping the rule absolute leaves nothing to argue about.
ALLOW = set()

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")


def offenders(text):
    """Any non-ASCII character in shipped source is a finding."""
    out = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp < 0x80:
            continue
        line = text[:i].count("\n") + 1
        out.append((line, hex(cp), unicodedata.name(ch, "?")))
    return out


print("shipped files")
for rel in SHIPPED:
    p = ROOT / rel
    if not p.exists():
        continue
    bad = offenders(p.read_text(encoding="utf-8", errors="replace"))
    chk(f"{rel}", not bad, bad[:3] or "clean")

print("rendered DOM (server must be running)")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto("http://127.0.0.1:8000", wait_until="networkidle")
        pg.wait_for_selector(".tool", timeout=10000)
        pg.wait_for_timeout(600)
        seen = {}
        for key in ("", "compress", "merge", "protect", "split", "office-to-pdf"):
            pg.goto(f"http://127.0.0.1:8000/#{key}", wait_until="networkidle")
            pg.wait_for_timeout(500)
            txt = pg.evaluate("() => document.body.innerText")
            for _, cp, nm in offenders(txt):
                seen[cp] = nm
        chk("all rendered text", not seen, list(seen.items())[:4] or "clean")
        b.close()
except ImportError:
    print("  SKIP  playwright not installed")

print(f"\n{ok} passed, {fail} failed")
if fail:
    sys.exit(f"{fail} emoji check(s) failed")
print("EMOJI-FREE")
