"""Computed-style audit of the rendered design. Needs server running."""
from playwright.sync_api import sync_playwright

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1360, "height": 1000})
    pg.goto("http://127.0.0.1:8000", wait_until="networkidle")
    pg.wait_for_selector(".tool", timeout=10000)
    pg.wait_for_timeout(700)

    print("bento grid geometry")
    g = pg.evaluate("""() => {
      const grid = document.querySelector('.grid');
      const s = getComputedStyle(grid);
      const cards = [...grid.querySelectorAll('.tool')].map(c => {
        const r = c.getBoundingClientRect();
        return { w: Math.round(r.width), h: Math.round(r.height), feat: c.classList.contains('feat') };
      });
      return { cols: s.gridTemplateColumns.split(' ').length,
               gap: parseFloat(s.gap), cards };
    }""")
    chk("4 columns at 1360px", g["cols"] == 4, g["cols"])
    chk("gap on 4px grid", g["gap"] % 4 == 0, f"{g['gap']}px")
    feat = [c for c in g["cards"] if c["feat"]]
    plain = [c for c in g["cards"] if not c["feat"]]
    if feat and plain:
        chk("featured card is ~2x wide", feat[0]["w"] > plain[0]["w"] * 1.8,
            f"{plain[0]['w']} vs {feat[0]['w']}")
    chk("cards share one height per row",
        len({c["h"] for c in plain}) <= 2, sorted({c["h"] for c in plain}))

    print("logo rendering")
    lg = pg.evaluate("""() => {
      const els = [...document.querySelectorAll('.flow .lg svg')];
      const sizes = els.map(e => { const r = e.getBoundingClientRect();
        return Math.round(r.width) + 'x' + Math.round(r.height); });
      const painted = els.filter(e => {
        const r = e.getBoundingClientRect();
        return r.width > 4 && r.height > 4;
      }).length;
      const grads = document.querySelectorAll('.flow .lg linearGradient').length;
      return { n: els.length, painted, uniq: [...new Set(sizes)], grads };
    }""")
    chk("all format logos painted", lg["painted"] == lg["n"], f"{lg['painted']}/{lg['n']}")
    chk("logos one consistent size", len(lg["uniq"]) == 1, lg["uniq"])
    chk("gradients present", lg["grads"] >= lg["n"], f"{lg['grads']} gradients")

    print("typography scale")
    ty = pg.evaluate("""() => {
      const g = s => { const e = document.querySelector(s); if (!e) return null;
        const c = getComputedStyle(e);
        return { px: parseFloat(c.fontSize), lh: +(parseFloat(c.lineHeight)/parseFloat(c.fontSize)).toFixed(2),
                 w: c.fontWeight }; };
      return { h1: g('h1'), h2: g('.shead h2'), h3: g('.tool h3'),
               body: g('.tool p'), lead: g('.hero > p') };
    }""")
    chk("h1 is the largest", ty["h1"]["px"] > ty["h2"]["px"] > ty["h3"]["px"],
        f"{ty['h1']['px']}/{ty['h2']['px']}/{ty['h3']['px']}")
    chk("h1 tight leading", ty["h1"]["lh"] <= 1.3, ty["h1"]["lh"])
    chk("body comfortable leading", 1.4 <= ty["body"]["lh"] <= 1.7, ty["body"]["lh"])
    chk("card body >= 12px", ty["body"]["px"] >= 12, f"{ty['body']['px']}px")
    chk("headings bold", int(ty["h1"]["w"]) >= 700, ty["h1"]["w"])

    print("hover affordance")
    before = pg.evaluate("""() => { const c = document.querySelector('.tool');
      return getComputedStyle(c).boxShadow; }""")
    pg.hover(".tool")
    pg.wait_for_timeout(450)
    after = pg.evaluate("""() => { const c = document.querySelector('.tool');
      const s = getComputedStyle(c);
      return { shadow: s.boxShadow, transform: s.transform, border: s.borderTopColor }; }""")
    chk("hover changes elevation", after["shadow"] != before, "shadow grows")
    chk("hover lifts the card", after["transform"] != "none", after["transform"])

    print("touch targets")
    t = pg.evaluate("""() => {
      const r = {};
      for (const sel of ['.tool', '.iconbtn', '.tnav a', '.find input']) {
        const e = document.querySelector(sel);
        if (e) { const b = e.getBoundingClientRect();
          r[sel] = [Math.round(b.width), Math.round(b.height)]; }
      }
      return r;
    }""")
    for sel, (w, h) in t.items():
        chk(f"{sel} >= 30px tall", h >= 30, f"{w}x{h}")

    print("sticky header")
    pg.evaluate("scrollTo(0, 1200)")
    pg.wait_for_timeout(450)
    st = pg.evaluate("""() => { const e = document.querySelector('.top');
      const r = e.getBoundingClientRect();
      return { top: Math.round(r.top), pos: getComputedStyle(e).position }; }""")
    chk("header stays pinned", st["pos"] == "sticky" and st["top"] == 0, st)
    spy = pg.evaluate("() => document.querySelectorAll('#tnav a.on').length")
    chk("scroll-spy marks one category", spy == 1, f"{spy} active")

    print("workspace layout")
    pg.evaluate("scrollTo(0, 0)")
    pg.click('.tool[data-k="merge"]')
    pg.wait_for_timeout(600)
    w = pg.evaluate("""() => {
      const s = getComputedStyle(document.querySelector('.work'));
      const side = getComputedStyle(document.querySelector('.side'));
      return { cols: s.gridTemplateColumns.split(' ').map(v => Math.round(parseFloat(v))),
               sticky: side.position };
    }""")
    chk("two-column work area", len(w["cols"]) == 2, w["cols"])
    chk("main column is wider", w["cols"][0] > w["cols"][1], w["cols"])
    chk("action rail sticky", w["sticky"] == "sticky", w["sticky"])

    print("category color actually applied")
    cc = pg.evaluate("""() => {
      const out = {};
      for (const sec of document.querySelectorAll('.sec')) {
        const tile = sec.querySelector('.tool .tile');
        if (tile) out[sec.id] = getComputedStyle(tile).backgroundColor;
      }
      return out;
    }""")
    pg.click("#back")
    pg.wait_for_timeout(400)
    cc = pg.evaluate("""() => {
      const out = {};
      for (const sec of document.querySelectorAll('.sec')) {
        const tile = sec.querySelector('.tool .tile');
        if (tile) out[sec.id] = getComputedStyle(tile).backgroundColor;
      }
      return out;
    }""")
    chk("each category has its own hue", len(set(cc.values())) == 4, len(set(cc.values())))

    b.close()

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} design check(s) failed"
print("DESIGN OK")
