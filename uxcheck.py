"""Reviewer pass: things a real user hits that assertions usually miss.
Needs server running + playwright. Creates its own fixtures."""
import os
import shutil
import tempfile

import pymupdf
from playwright.sync_api import sync_playwright

TMP = tempfile.mkdtemp(prefix="ux_")


def _pdf(name, pages=4):
    d = pymupdf.open()
    for i in range(pages):
        d.new_page().insert_text((72, 100), f"Review page {i + 1}", fontsize=13)
    p = os.path.join(TMP, name)
    d.save(p)
    d.close()
    return p


def _png(name):
    from PIL import Image
    p = os.path.join(TMP, name)
    Image.new("RGB", (800, 600), (40, 70, 160)).save(p)
    return p


SAMPLE = _pdf("sample_for_review.pdf")
LONGNAME = _pdf("a-really-very-extremely-long-document-name-for-testing-overflow.pdf")
IMAGE = _png("not-a-document.png")

notes = []


def flag(sev, what, detail=""):
    notes.append((sev, what, detail))
    print(f"  [{sev}] {what}" + (f"\n        {detail}" if detail else ""))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1360, "height": 1000})
    pg.goto("http://127.0.0.1:8000", wait_until="networkidle")
    pg.wait_for_selector(".tool", timeout=10000)
    pg.wait_for_timeout(700)

    print("=" * 70)
    print("CLARITY OF LABELS")
    print("=" * 70)
    cards = pg.evaluate("""() => [...document.querySelectorAll('.tool')].map(c => ({
      title: c.querySelector('h3').innerText,
      desc: c.querySelector('p').innerText,
      tag: c.querySelector('.tag')?.innerText || ''
    }))""")
    titles = [c["title"] for c in cards]
    dupes = {t for t in titles if titles.count(t) > 1}
    flag("PASS" if not dupes else "MED", "tool names are unique",
         f"duplicates: {dupes}" if dupes else f"{len(titles)} distinct")

    jargon = [c["title"] for c in cards
              if any(w in c["desc"].lower() for w in ("buffer", "stream", "endpoint", "api", "bytesio"))]
    flag("PASS" if not jargon else "LOW", "descriptions avoid internal jargon", jargon or "clean")

    longd = [(c["title"], len(c["desc"])) for c in cards if len(c["desc"]) > 95]
    flag("PASS" if not longd else "LOW", "descriptions fit the card", longd or "all under 95 chars")

    print()
    print("=" * 70)
    print("DISCOVERABILITY")
    print("=" * 70)
    for term, expect in [("word", "pdf-to-docx"), ("excel", "pdf-to-xlsx"),
                         ("jpg", "pdf-to-images"), ("password", "protect"),
                         ("compress", "compress"), ("combine", "merge"),
                         ("smaller", "compress"), ("lock", "protect"),
                         ("shrink", "compress"), ("rotate", "rotate"),
                         ("encrypt", "protect"), ("zip", "split")]:
        pg.fill("#q", term)
        pg.wait_for_timeout(260)
        keys = pg.evaluate("() => [...document.querySelectorAll('.tool:not([hidden])')].map(c => c.dataset.k)")
        hit = expect in keys
        flag("PASS" if hit else "MED", f"search '{term}' finds {expect}",
             "" if hit else f"got {keys[:4] or 'nothing'}")
    pg.fill("#q", "")
    pg.wait_for_timeout(300)

    print()
    print("=" * 70)
    print("KEYBOARD ONLY")
    print("=" * 70)
    pg.keyboard.press("Tab")
    order = []
    for _ in range(9):
        info = pg.evaluate("""() => { const e = document.activeElement;
          const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
          return { tag: e.tagName, cls: (e.className||'').split(' ')[0],
                   label: (e.innerText||e.getAttribute('aria-label')||e.placeholder||'').slice(0,26),
                   ring: s.outlineWidth, vis: r.width > 0 && r.height > 0 }; }""")
        order.append(info)
        pg.keyboard.press("Tab")
    noring = [o for o in order if o["ring"] in ("0px", "") and o["vis"]]
    flag("PASS" if not noring else "MED", "every focus stop shows a ring",
         [o["cls"] for o in noring] or "all visible")
    invisible = [o for o in order if not o["vis"]]
    flag("PASS" if not invisible else "LOW", "no focus stop is invisible",
         [o["cls"] for o in invisible] or "none")
    print("        tab order: " + " -> ".join(
        (o["label"] or o["cls"] or o["tag"])[:16] for o in order[:7]))

    reachable = pg.evaluate("""() => {
      const first = document.querySelector('.tool');
      first.focus();
      return document.activeElement === first;
    }""")
    flag("PASS" if reachable else "HIGH", "tool cards are focusable")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(500)
    flag("PASS" if pg.is_visible("#workspace") else "HIGH",
         "Enter on a card opens the tool")

    print()
    print("=" * 70)
    print("ERROR MESSAGE QUALITY")
    print("=" * 70)
    pg.goto("http://127.0.0.1:8000/#watermark", wait_until="networkidle")
    pg.wait_for_timeout(600)
    pg.set_input_files("#picker", IMAGE)
    pg.wait_for_timeout(500)
    if pg.is_visible(".note.e"):
        msg = pg.inner_text(".note.e")
        names = "not-a-document" in msg or "png" in msg.lower()
        tells = any(w in msg.lower() for w in ("need", "must", "only", "not"))
        flag("PASS" if names and tells else "LOW",
             "wrong-type error names the file and the rule", msg[:95])
    else:
        flag("MED", "wrong file type produced no visible error")

    pg.goto("http://127.0.0.1:8000/#unlock", wait_until="networkidle")
    pg.wait_for_timeout(500)
    hint = pg.evaluate("() => document.querySelector('.hint')?.innerText || ''")
    flag("PASS" if "cannot" in hint.lower() or "know" in hint.lower() else "LOW",
         "Unlock sets the right expectation", hint[:80])

    print()
    print("=" * 70)
    print("STATE AFTER ACTIONS")
    print("=" * 70)
    pg.goto("http://127.0.0.1:8000/#merge", wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.set_input_files("#picker", [IMAGE])
    pg.wait_for_timeout(400)
    st = pg.evaluate("""() => ({
      rows: document.querySelectorAll('.flist li').length,
      dropVisible: !document.getElementById('dropwrap').hidden,
      goDisabled: document.getElementById('go').disabled,
      goText: document.getElementById('gotxt').innerText,
    })""")
    flag("PASS" if st["rows"] == 0 and st["dropVisible"] else "MED",
         "rejected file leaves the dropzone up", st)

    pg.goto("http://127.0.0.1:8000/#compress", wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.set_input_files("#picker", SAMPLE)
    pg.wait_for_timeout(500)
    pg.click(".mini.dg")
    pg.wait_for_timeout(400)
    st = pg.evaluate("""() => ({
      rows: document.querySelectorAll('.flist li').length,
      dropVisible: !document.getElementById('dropwrap').hidden,
      goDisabled: document.getElementById('go').disabled,
    })""")
    flag("PASS" if st["rows"] == 0 and st["dropVisible"] and st["goDisabled"] else "MED",
         "removing the only file restores the empty state", st)

    print()
    print("=" * 70)
    print("TEXT OVERFLOW WITH A VERY LONG NAME")
    print("=" * 70)
    pg.set_input_files("#picker", LONGNAME)
    pg.wait_for_timeout(500)
    ov = pg.evaluate("""() => {
      const row = document.querySelector('.flist li');
      if (!row) return null;
      const nm = row.querySelector('.fn');
      return { rowRight: Math.round(row.getBoundingClientRect().right),
               nameRight: Math.round(nm.getBoundingClientRect().right),
               clipped: getComputedStyle(nm).textOverflow,
               docScroll: document.documentElement.scrollWidth,
               docClient: document.documentElement.clientWidth };
    }""")
    if ov:
        safe = ov["nameRight"] <= ov["rowRight"] + 1 and ov["docScroll"] <= ov["docClient"] + 1
        flag("PASS" if safe else "MED", "long filename is ellipsised, not overflowing", ov)

    print()
    print("=" * 70)
    print("MOBILE REACHABILITY")
    print("=" * 70)
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.goto("http://127.0.0.1:8000", wait_until="networkidle")
    pg.wait_for_timeout(700)
    m = pg.evaluate("""() => {
      const nav = document.querySelector('.tnav');
      const navHidden = getComputedStyle(nav).display === 'none';
      const smalls = [...document.querySelectorAll('button, a, input, select')]
        .filter(e => { const r = e.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && r.height < 32; })
        .map(e => (e.className||e.tagName) + ':' + Math.round(e.getBoundingClientRect().height));
      return { navHidden, smalls: smalls.slice(0, 6), count: smalls.length };
    }""")
    flag("PASS" if m["navHidden"] else "LOW", "desktop category nav hides on mobile")
    flag("PASS" if m["count"] == 0 else "LOW",
         "no tap target under 32px tall", m["smalls"] or "all >= 32px")

    first = pg.evaluate("""() => {
      const c = document.querySelector('.tool'); const r = c.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top) };
    }""")
    flag("PASS" if first["w"] >= 300 else "LOW", "cards use the mobile width", first)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    counts = {}
    for sev, *_ in notes:
        counts[sev] = counts.get(sev, 0) + 1
    for k in ("HIGH", "MED", "LOW", "PASS"):
        if k in counts:
            print(f"  {k:5} {counts[k]}")
    todo = [n for n in notes if n[0] in ("HIGH", "MED", "LOW")]
    if todo:
        print("\nACTIONABLE:")
        for sev, what, _ in todo:
            print(f"  [{sev}] {what}")
    else:
        print("\nNo actionable findings.")

    b.close()

shutil.rmtree(TMP, ignore_errors=True)
assert not [n for n in notes if n[0] in ("HIGH", "MED")], "reviewer found blocking issues"
print("UX OK")
