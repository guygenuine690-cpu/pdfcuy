"""The repository is public now, so every tracked byte is readable by anyone.

This asserts that nothing private is in it. The absence of a secret is easy to
believe and easy to be wrong about, so it gets checked rather than assumed.
"""
import io
import os
import re
import subprocess
import sys

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


def git(*a):
    r = subprocess.run(("git",) + a, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout


tracked = [p for p in git("ls-files").splitlines() if p.strip()]

print("the working tree is what was published")
chk("files are tracked", len(tracked) > 30, len(tracked))
chk("nothing uncommitted", not git("status", "--porcelain").strip(),
    git("status", "--porcelain").strip()[:120])

print("\nno credential is in any tracked file")
# Patterns for things that actually grant access. Generic words like "token"
# appear in legitimate code, so the shapes are matched, not the vocabulary.
SECRET = [
    ("GitHub PAT", r"gh[pousr]_[A-Za-z0-9]{16,}"),
    ("Vercel token", r"\bvercel_[A-Za-z0-9]{20,}"),
    ("AWS key id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("OpenAI key", r"\bsk-[A-Za-z0-9]{32,}"),
    ("Google key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer literal", r"[Bb]earer\s+[A-Za-z0-9._-]{24,}"),
    ("basic auth URL", r"https?://[^/\s:@]+:[^/\s@]+@"),
]
hits = []
for p in tracked:
    if os.path.basename(p) == os.path.basename(__file__):
        continue          # the patterns live here; it would match itself
    try:
        t = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for label, pat in SECRET:
        for m in re.finditer(pat, t):
            hits.append(f"{p}: {label}: {m.group(0)[:18]}...")
for label, _ in SECRET:
    chk(f"no {label}", not any(label in h for h in hits),
        next((h for h in hits if label in h), ""))

print("\nno personal path or machine detail")
# This file carries the patterns it searches for, so scanning it finds its own
# needles. A detector that trips on its own definition is noise.
SELF_FILE = os.path.basename(__file__)
HOME_USER = re.escape(os.path.basename(os.path.expanduser("~")).split()[0])
leaks = []
for p in tracked:
    if os.path.basename(p) == SELF_FILE:
        continue
    try:
        t = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for pat, what in [(r"C:\\Users\\[A-Za-z]", "windows home path"),
                      (r"/home/[a-z]", "unix home path"),
                      (HOME_USER, "the machine owner's name")]:
        if re.search(pat, t):
            leaks.append(f"{p}: {what}")
chk("no absolute home path or user name", not leaks, leaks[:4])

print("\nthe ignore rules actually hold")
gi = io.open(".gitignore", encoding="utf-8").read()
for pat in [".env", "__pycache__", "*.png", ".vercel"]:
    chk(f"{pat} ignored", pat in gi)
chk("no .env tracked", not [p for p in tracked if ".env" in p])
chk("no scratch scripts tracked",
    not [p for p in tracked if os.path.basename(p).startswith("_")],
    [p for p in tracked if os.path.basename(p).startswith("_")][:4])
chk("no .vercel link tracked", not [p for p in tracked if ".vercel/" in p])
chk("no binary image tracked",
    not [p for p in tracked if p.lower().endswith((".png", ".jpg"))])

print("\nhistory is clean too, not just the tip")
# A secret removed in a later commit is still public in the history.
log = git("log", "--all", "--format=%H", "--name-only")
old = [ln for ln in log.splitlines()
       if ln.endswith(".png") or ".env" in ln
       or os.path.basename(ln).startswith("_") and ln.endswith(".py")]
chk("no secret-ish file ever committed", not old, old[:4])
msgs = git("log", "--all", "--format=%s%n%b")
mhits = [lbl for lbl, pat in SECRET if re.search(pat, msgs)]
chk("no credential in a commit message", not mhits, mhits)

print(f"\n{ok} passed, {fail} failed")
if fail:
    print("PUBLIC REPO LEAK", file=sys.stderr)
assert fail == 0, f"{fail} check(s) failed"
print("PUBLIC OK")
