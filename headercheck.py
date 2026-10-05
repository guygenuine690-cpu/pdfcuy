"""Is the category nav actually centred on the page, and is the lockup clean?"""
from playwright.sync_api import sync_playwright

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}" + (f"  {extra}" if extra else ""))
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    pg.wait_for_timeout(700)

    print("the nav sits on the real centre of the header")
    nav = pg.evaluate("""() => {
      const n = document.querySelector('#tnav');
      const bar = document.querySelector('.topin');
      const r = n.getBoundingClientRect(), br = bar.getBoundingClientRect();
      return {navMid: r.left + r.width / 2, barMid: br.left + br.width / 2,
              items: n.querySelectorAll('a').length, w: r.width,
              cols: getComputedStyle(bar).gridTemplateColumns};
    }""")
    off = abs(nav["navMid"] - nav["barMid"])
    chk("categories are present", nav["items"] >= 4, f"{nav['items']} links")
    chk("nav centre matches the bar centre", off < 1.5, f"off by {off:.2f}px")
    chk("the header is a grid, not a flex row with spacers",
        "px" in nav["cols"] and len(nav["cols"].split()) == 3, nav["cols"])

    print("\nthe nav does not collide with the brand or the controls")
    gaps = pg.evaluate("""() => {
      const r = s => document.querySelector(s).getBoundingClientRect();
      return {left: r('#tnav').left - r('.brand').right,
              right: r('.tend').left - r('#tnav').right};
    }""")
    chk("clear of the brand", gaps["left"] > 8, f"{gaps['left']:.0f}px gap")
    chk("clear of the controls", gaps["right"] > 8, f"{gaps['right']:.0f}px gap")

    print("\nthe wordmark is one line, no tagline under it")
    mark = pg.evaluate("""() => {
      const n = document.querySelector('.brand .n');
      return {text: n.innerText.trim(), italics: n.querySelectorAll('i').length,
              lines: n.getBoundingClientRect().height,
              w1: getComputedStyle(n.querySelector('.w1')).color,
              w2: getComputedStyle(n.querySelector('.w2')).color};
    }""")
    chk("reads PDFCUY", mark["text"] == "PDFCUY", repr(mark["text"]))
    chk("no tagline element left", mark["italics"] == 0, mark["italics"])
    chk("single line height", mark["lines"] < 30, f"{mark['lines']:.0f}px")
    chk("the two halves differ in colour", mark["w1"] != mark["w2"],
        f"{mark['w1']} vs {mark['w2']}")

    print("\ncapitals need positive tracking, not the negative kind")
    track = pg.evaluate("""() => {
      const b = document.querySelector('.brand b');
      const f = document.querySelector('.fbrand');
      const px = el => parseFloat(getComputedStyle(el).letterSpacing) || 0;
      return {header: px(b), footer: px(f),
              upper: getComputedStyle(f).textTransform};
    }""")
    chk("header wordmark is not negatively tracked", track["header"] > 0,
        f"{track['header']:.2f}px")
    chk("footer wordmark matches it", track["footer"] > 0,
        f"{track['footer']:.2f}px")

    print("\nthe tab title and footer carry the new name")
    chk("tab title", "PDFCUY" in pg.title(), pg.title())
    chk("footer heading", "PDFCUY" in pg.inner_text("footer"),
        pg.inner_text(".fbrand"))
    # The name is an acronym-style wordmark, so caps are intentional. Assert the
    # exact string rather than a case-insensitive match, or a half-renamed
    # "pdfCUY" would slip through.
    chk("footer uses the same capitalisation as the header",
        pg.inner_text(".fbrand").strip() == "PDFCUY",
        repr(pg.inner_text(".fbrand").strip()))
    chk("old name gone from the page", "anondocs" not in
        pg.content().lower().replace("anon docs", "anondocs"))

    print("\nnarrow viewport: the middle track must not leave a hole")
    for w, expect_nav in ((1200, True), (880, False), (420, False)):
        pg.set_viewport_size({"width": w, "height": 900})
        pg.wait_for_timeout(350)
        res = pg.evaluate("""() => {
          const bar = document.querySelector('.topin');
          const n = document.querySelector('#tnav');
          const r = s => document.querySelector(s).getBoundingClientRect();
          const cs = getComputedStyle(bar);
          return {shown: cs.display !== 'none' && getComputedStyle(n).display !== 'none',
                  cols: cs.gridTemplateColumns.split(' ').length,
                  brandLeft: r('.brand').left, barLeft: bar.getBoundingClientRect().left,
                  pad: parseFloat(cs.paddingLeft),
                  overflow: document.documentElement.scrollWidth >
                            document.documentElement.clientWidth};
        }""")
        chk(f"{w}px: nav {'shown' if expect_nav else 'hidden'}",
            res["shown"] == expect_nav, f"display shown={res['shown']}")
        # The bar has horizontal padding, so the brand sits one padding width in.
        # That is the intended inset, not a centring bug.
        inset = res["brandLeft"] - res["barLeft"]
        chk(f"{w}px: brand sits exactly one padding in from the edge",
            abs(inset - res["pad"]) < 2, f"{inset:.0f}px vs {res['pad']:.0f}px padding")
        chk(f"{w}px: no horizontal overflow", not res["overflow"])
        if not expect_nav:
            chk(f"{w}px: two tracks, no empty middle", res["cols"] == 2,
                f"{res['cols']} tracks")

    chk("no script errors", not errs, str(errs[:2]))
    b.close()

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} check(s) failed"
print("HEADER OK")
