"""WCAG contrast audit for the PDFCUY palette. No server needed."""

ok = fail = 0


def HEX(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def chk(label, got, need):
    global ok, fail
    good = got >= need
    ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
    print(f"  {'PASS' if good else 'FAIL'}  {label:<42} {got:5.2f}:1  (need {need})")


print("LIGHT - card #ffffff, page #f4f5fa, soft #f3f4f9")
CARD, PAGE, SOFT = HEX("#ffffff"), HEX("#f4f5fa"), HEX("#f3f4f9")
for label, fg, bg, need in [
    ("ink  #14161f body on card", HEX("#14161f"), CARD, 4.5),
    ("ink  #14161f body on page", HEX("#14161f"), PAGE, 4.5),
    ("ink-2 #565e73 secondary on card", HEX("#565e73"), CARD, 4.5),
    ("ink-2 #565e73 secondary on soft", HEX("#565e73"), SOFT, 4.5),
    ("ink-3 #848da4 meta on card", HEX("#848da4"), CARD, 3.0),
    ("ink-3 #848da4 meta on soft", HEX("#848da4"), SOFT, 3.0),
    ("br   #4f46e5 brand on card", HEX("#4f46e5"), CARD, 4.5),
    ("br   #4f46e5 brand on br-soft", HEX("#4f46e5"), HEX("#eef0fe"), 3.0),
    # The "cuy" half of the wordmark is brand-coloured and sits on the sticky
    # header, which uses --page rather than --card.
    ("br   #4f46e5 wordmark on page", HEX("#4f46e5"), PAGE, 4.5),
    ("ink  #14161f wordmark on page", HEX("#14161f"), PAGE, 4.5),
    ("c1   #2563eb convert on card", HEX("#2563eb"), CARD, 4.5),
    ("c1   #2563eb convert on c1s", HEX("#2563eb"), HEX("#e8efff"), 3.0),
    ("c2   #c2410c organize on card", HEX("#c2410c"), CARD, 4.5),
    ("c2   #c2410c organize on c2s", HEX("#c2410c"), HEX("#fdeee4"), 3.0),
    ("c3   #047857 optimize on card", HEX("#047857"), CARD, 4.5),
    ("c3   #047857 optimize on c3s", HEX("#047857"), HEX("#e2f6ee"), 3.0),
    ("c4   #be185d secure on card", HEX("#be185d"), CARD, 4.5),
    ("c4   #be185d secure on c4s", HEX("#be185d"), HEX("#fdeaf2"), 3.0),
    ("ok   #047857 success on ok-s", HEX("#047857"), HEX("#e2f6ee"), 4.5),
    ("err  #be1f1f error on err-s", HEX("#be1f1f"), HEX("#fdeaea"), 4.5),
    ("warn #9a5b00 warning on warn-s", HEX("#9a5b00"), HEX("#fdf2e0"), 4.5),
]:
    chk(label, ratio(fg, bg), need)
print("  -- white text on colored fills (tool tile hover, badges, CTA)")
for label, bg in [("on br #4f46e5", "#4f46e5"), ("on c1 #2563eb", "#2563eb"),
                  ("on c2 #c2410c", "#c2410c"), ("on c3 #047857", "#047857"),
                  ("on c4 #be185d", "#be185d")]:
    chk(f"card #ffffff {label}", ratio(HEX("#ffffff"), HEX(bg)), 4.5)

print("\nDARK - card #161a25, page #0b0d14, soft #1d2230")
CARDD, PAGED, SOFTD = HEX("#161a25"), HEX("#0b0d14"), HEX("#1d2230")
for label, fg, bg, need in [
    ("ink  #edeff6 body on card", HEX("#edeff6"), CARDD, 4.5),
    ("ink  #edeff6 body on page", HEX("#edeff6"), PAGED, 4.5),
    ("ink-2 #a8b0c4 secondary on card", HEX("#a8b0c4"), CARDD, 4.5),
    ("ink-2 #a8b0c4 secondary on soft", HEX("#a8b0c4"), SOFTD, 4.5),
    ("ink-3 #7c8499 meta on card", HEX("#7c8499"), CARDD, 3.0),
    ("ink-3 #7c8499 meta on soft", HEX("#7c8499"), SOFTD, 3.0),
    ("br   #8b84f8 brand on card", HEX("#8b84f8"), CARDD, 4.5),
    ("br   #8b84f8 brand on br-soft", HEX("#8b84f8"), HEX("#1e2039"), 3.0),
    ("br   #8b84f8 wordmark on page", HEX("#8b84f8"), HEX("#0b0d14"), 4.5),
    ("ink  #edeff6 wordmark on page", HEX("#edeff6"), HEX("#0b0d14"), 4.5),
    ("c1   #7aa6ff convert on card", HEX("#7aa6ff"), CARDD, 4.5),
    ("c1   #7aa6ff convert on c1s", HEX("#7aa6ff"), HEX("#16213c"), 3.0),
    ("c2   #f59e63 organize on card", HEX("#f59e63"), CARDD, 4.5),
    ("c2   #f59e63 organize on c2s", HEX("#f59e63"), HEX("#2e1d12"), 3.0),
    ("c3   #4fc996 optimize on card", HEX("#4fc996"), CARDD, 4.5),
    ("c3   #4fc996 optimize on c3s", HEX("#4fc996"), HEX("#0f2a21"), 3.0),
    ("c4   #f4719f secure on card", HEX("#f4719f"), CARDD, 4.5),
    ("c4   #f4719f secure on c4s", HEX("#f4719f"), HEX("#2e1423"), 3.0),
    ("ok   #4fc996 success on ok-s", HEX("#4fc996"), HEX("#0f2a21"), 4.5),
    ("err  #f4756f error on err-s", HEX("#f4756f"), HEX("#2d1515"), 4.5),
    ("warn #dfa24a warning on warn-s", HEX("#dfa24a"), HEX("#2a1f0d"), 4.5),
]:
    chk(label, ratio(fg, bg), need)
print("  -- dark text on colored fills")
for label, bg in [("on br #8b84f8", "#8b84f8"), ("on c1 #7aa6ff", "#7aa6ff"),
                  ("on c2 #f59e63", "#f59e63"), ("on c3 #4fc996", "#4fc996"),
                  ("on c4 #f4719f", "#f4719f")]:
    chk(f"card #161a25 {label}", ratio(CARDD, HEX(bg)), 4.5)

print(f"\n{ok} passed, {fail} failed")
assert fail == 0, f"{fail} contrast check(s) failed"
print("CONTRAST OK (WCAG AA)")
