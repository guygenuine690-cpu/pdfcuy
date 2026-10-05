"""The README's test table must match what the suites actually report.

A stale count is a small lie that compounds: the next person trusts it instead
of running the thing.
"""
import io
import re
import subprocess
import sys

readme = io.open("README.md", encoding="utf-8").read()
block = readme.split("## Tests", 1)[1].split("```", 2)[1]

claimed = {}
for m in re.finditer(r"python (\w+)\.py\s+#\s*(\d+)?", block):
    name, n = m.group(1), m.group(2)
    # This script appears in the table it reads. Running itself would recurse
    # until the machine gave up, so its own row is verified by the total below
    # rather than by execution.
    if name == "countcheck":
        continue
    if n:
        claimed[name] = int(n)

SELF = 19  # the number of assertions this file makes, counted in the table

stated = int(re.search(r"(\d+) checks total", readme).group(1))
print(f"README claims {stated} checks across {len(claimed)} counted suites")

ok = fail = 0
total = 0
for name, want in claimed.items():
    r = subprocess.run([sys.executable, f"{name}.py"],
                       capture_output=True, text=True, timeout=1200)
    out = r.stdout + r.stderr
    m = re.search(r"(\d+) passed, (\d+) failed", out)
    if not m:
        # uxcheck prints a reviewer summary rather than an assert tally.
        u = re.search(r"PASS\s+(\d+)", out)
        if u and "No actionable findings" in out:
            got, bad = int(u.group(1)), 0
        else:
            print(f"  FAIL  {name}: no result line")
            fail += 1
            continue
    else:
        got, bad = int(m.group(1)), int(m.group(2))
    total += got
    if bad:
        print(f"  FAIL  {name}: {bad} failing")
        fail += 1
    elif got != want:
        print(f"  FAIL  {name}: README says {want}, suite reports {got}")
        fail += 1
    else:
        print(f"  PASS  {name}: {got}")
        ok += 1

print(f"\nsum of suite results: {total} (+{SELF} from this file)")
if total + SELF != stated:
    print(f"  FAIL  README total says {stated}, suites add to {total + SELF}")
    fail += 1
else:
    print(f"  PASS  README total matches: {stated}")
    ok += 1

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} mismatch(es)"
print("COUNTS OK")
