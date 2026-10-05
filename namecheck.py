"""Unit tests for safe_stem and disposition, loaded without importing app."""
import io
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

src = io.open("app.py", encoding="utf-8").read()
ns = {"re": re, "Path": Path, "quote": quote, "unicodedata": unicodedata}
i = src.find("_UNSAFE = re.compile")
j = src.find("async def grab")
exec(src[i:j], ns)
safe_stem, disposition = ns["safe_stem"], ns["disposition"]

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"  {'PASS' if cond else 'FAIL'}  {label} {extra}")


HOSTILE = [
    "../../../../etc/passwd.pdf",
    "..\\..\\windows\\system32\\evil.pdf",
    'bad"\r\nX-Injected: yes.pdf',
    'a"b;filename="other.pdf',
    "<script>alert(1)</script>.pdf",
    "doc\u202egnp.pdf",
    "A" * 300 + ".pdf",
    "ok\x00.pdf",
    "",
    "...",
    "   ",
    "%00%2e%2e%2f.pdf",
    "file\twith\ttabs.pdf",
    "\r\n\r\nSet-Cookie: a=b.pdf",
]
print("safe_stem resists hostile names")
DANGER = ['..', '/', '\\', '"', '\r', '\n', '\x00', '<', '>', ';', ':']
for c in HOSTILE:
    r = safe_stem(c)
    hits = [x for x in DANGER if x in r]
    chk(f"{c[:34]!r}", not hits and bool(r), f"-> {r!r}")

print("safe_stem keeps real names usable")
for raw, want in [
    ("report final v2.pdf", "report final v2"),
    ("faktur-2024_01.PDF", "faktur-2024_01"),
    ("Laporan (revisi).pdf", "Laporan (revisi)"),
    ("\u4e2d\u6587\u6587\u6863.pdf", "\u4e2d\u6587\u6587\u6863"),
    ("\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442.pdf", "\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442"),
    ("r\u00e9sum\u00e9.pdf", "r\u00e9sum\u00e9"),
]:
    got = safe_stem(raw)
    chk(f"{raw!r} preserved", got == want, f"-> {got!r}")

print("disposition header is always header-safe")
for raw in HOSTILE + ["\u4e2d\u6587.pdf", "r\u00e9sum\u00e9_compressed.pdf", "ok.pdf"]:
    h = disposition(safe_stem(raw) + ".pdf")
    bad = [x for x in ['\r', '\n', '\x00'] if x in h]
    structure = h.startswith('attachment; filename="') and "filename*=UTF-8''" in h
    quoted = h.count('"') == 2
    chk(f"{raw[:30]!r}", not bad and structure and quoted, h[:76])

print("disposition round-trips unicode")
h = disposition("\u4e2d\u6587\u6587\u6863.pdf")
chk("utf-8 variant carries real name", "%E4%B8%AD%E6%96%87" in h, h[:92])
chk("ascii fallback is pure ascii", h.split('"')[1].isascii(), h.split('"')[1])

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} filename check(s) failed"
print("FILENAME OK")
