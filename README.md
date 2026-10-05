# PDFCUY

Anonymous document toolkit. Everything runs in memory, nothing is stored, nothing is logged,
no account required.

## Run

```bash
pip install -r requirements.txt
python app.py              # http://127.0.0.1:8000
```

Production:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 --no-access-log
```

Put it behind a TLS reverse proxy (Caddy or nginx) so uploads are encrypted in transit.

## Two conversion engines

| Engine | When it runs | Coverage |
|---|---|---|
| LibreOffice | used automatically when `soffice` is on PATH | every format including `.doc .xls .ppt .odt .ods .odp .rtf .html`, high layout fidelity |
| Built-in (pure Python) | fallback when LibreOffice is absent | `.docx .xlsx .pptx .csv .txt .md` |

Engine status shows in the header. To enable LibreOffice, install it and restart the server:
`winget install TheDocumentFoundation.LibreOffice`, or point `SOFFICE_BIN` at `soffice.exe`.

## Tools

Twenty-seven tools in four categories. Pick one from the grid, then drop your file.

**Convert** (9) - Office to PDF, PDF to Word, PDF to Excel, PDF to PowerPoint,
PDF to JPG, JPG to PDF, HTML to PDF, PDF to Markdown, Convert anything.

**Organize** (8) - Merge, Split, Organize pages, Rotate, Remove pages, Extract pages,
Add page numbers, Crop.

**Optimize** (5) - Compress, Repair, Flatten, PDF to Text, Office to Text.

**Secure** (5) - Protect with AES-256, Unlock, Watermark, Redact, Sign.

Each card shows the formats it takes and the format you get back, as colored app-style
logos. The picker is filtered per tool, so a PNG cannot be handed to Compress PDF.

Search matches intent rather than labels only: "smaller" finds Compress, "combine" finds
Merge, "black out" finds Redact, "fix broken" finds Repair.

### Notes on four of them

**Compress** re-encodes the embedded raster images, which is where the bytes actually live.
An earlier version only ran garbage collection plus deflate and so shrank a scanned file by
0.1 percent, which is useless for the main reason people compress a PDF. Current results on a
1.2 MB scan: light 61 percent smaller, balanced 72 percent, strong 90 percent. Text and vector
art are never touched, images under 600 px are skipped, and if the result would be larger than
the input the original is returned unchanged.

**Redact** removes the glyphs, it does not draw a black box over them. Covering text leaves it
fully selectable and copyable, which is how redaction failures end up in the news. The tests
assert the words are gone from the extracted text afterwards.

**Watermark** takes text or your own logo, at any angle from -90 to 90, in seven positions, or
tiled across the page. Text is drawn with a morph matrix rather than `insert_textbox`, because
that call only honours 90-degree steps and a diagonal stamp is the usual request. Attaching a
logo hides the text field, since leaving both on screen implies they combine when the image
actually wins.

**Flatten** uses `Document.bake()`. Re-drawing each page with `show_pdf_page` looks correct and
produces a file with no form fields, but silently discards the values someone typed, because a
widget's text lives in its appearance stream rather than the page content. The test fills a
field with a name and asserts the name is still readable afterwards.

## Comparison with iLovePDF

Present here: merge, split, compress, remove pages, extract pages, organize, rotate, add page
numbers, crop, watermark (text or image), repair, flatten, protect, unlock, redact, sign,
HTML to PDF, PDF to Markdown, and the Office and image conversions in both directions.

Deliberately absent:

| Theirs | Why not here |
|---|---|
| OCR PDF | needs a Tesseract install, which is not bundled; shipping it would mean failing at runtime instead of being honest up front |
| Edit PDF, PDF Forms | needs a full visual editor, which is a different product |
| Compare PDF | needs side-by-side diff rendering |
| AI Summarizer, Translate | would send your document to a third-party model, which this site exists to avoid |
| Scan to PDF | needs camera access, which the CSP blocks on purpose |
| Signature requests, accounts | requires identity and storage, so no longer anonymous |

Sign here stamps a signature image. It is not a cryptographic signature, and the tool says so.

## Endpoints

```
GET  /                     UI
GET  /api/engines          {libreoffice: bool, builtin: true}
POST /api/info             file, password        -> {pages, encrypted}
POST /api/office-to-pdf    files[], combine
POST /api/convert          file, to              (to=pdf works without LibreOffice; others need it)
POST /api/office-text      file
POST /api/pdf-to-docx      file, pages, password
POST /api/pdf-to-xlsx      file, pages, password
POST /api/pdf-to-pptx      file, pages, dpi, password
POST /api/pdf-to-images    file, dpi, fmt, pages, password
POST /api/images-to-pdf    files[], size, margin
POST /api/merge            files[], password
POST /api/split            file, mode(extract|each|ranges), pages, password
POST /api/organize         file, pages, remove, password
POST /api/rotate           file, angle, pages, password
POST /api/compress         file, level(low|medium|high), password
POST /api/extract-text     file, pages, password
POST /api/watermark        file, text, image, opacity, fontsize, angle, place, tile, width, pages, password
POST /api/protect          file, new_password, allow_print, password
POST /api/unlock           file, password
POST /api/remove-pages     file, pages, password
POST /api/extract-pages    file, pages, password
POST /api/page-numbers     file, position, fmt, start, fontsize, pages, password
POST /api/crop             file, top, bottom, left, right, pages, password
POST /api/repair           file, password
POST /api/redact           file, words, match_case, pages, password
POST /api/sign             file, image, corner, page_no, width, password
POST /api/html-to-pdf      html or file, size(a4|letter|legal)
POST /api/pdf-to-markdown  file, pages, password
POST /api/flatten          file, password
```

Page syntax: `1-3,7,10-`. Blank means every page. Written order is output order, so `4,1`
puts page 4 first and `5-2` counts backwards. An explicit page past the end of the document is
an error rather than something dropped quietly: asking for page 99 of a 5-page file returns
`This document has 5 pages, so there is no page 99.` Otherwise the download looks like it
worked and the missing page is noticed much later. Ranges that merely overlap the end (`2-99`,
`9-2` on a short file) clamp instead, as do the open-ended forms `-3` and `7-`.

Page syntax: `1-3,7,10-`. Blank means every page. Written order is output order.

## Privacy and hardening

Every operation uses `BytesIO`. The only exceptions are PDF-to-Word and the LibreOffice path,
which need a file path; both use an OS temp directory removed in a `finally` block. A canary
test in `audit.py` writes a marker string into a PDF, runs it through those endpoints, then
scans every temp entry for that marker. Nothing persists.

`--no-access-log` suppresses request logging. No cookies, sessions, or analytics. The page
makes no outbound request: fonts are a system stack, icons are inline SVG, no CDN.

Response headers on every route, including static assets and error bodies:

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'none'` with `script-src`/`style-src` at `'self'`, no `unsafe-inline` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | geolocation, microphone, camera, usb, payment all denied |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` | `no-store` |

The `Server` header is removed. It names the stack and version for anyone shopping for a CVE
and tells a visitor nothing.

The CSP has no `unsafe-inline`, so the UI ships zero inline styles and zero inline scripts.
Per-category colors are classes (`.k1` to `.k4`), not style attributes. `uicheck.py` fails if
an inline style reappears, and `flowcheck.py` fails on any CSP violation in the console.

**Input handling.** Download names pass through `safe_stem()`, which strips directory parts,
control characters, quotes and CR/LF. `Content-Disposition` follows RFC 6266 with a pure-ASCII
`filename` plus a percent-encoded `filename*`, so `report.pdf` and the Cyrillic or CJK
equivalent both download correctly while no byte can terminate the header early.

**No silent fallbacks.** Unknown enum values and out-of-range numbers are rejected with a
message naming the valid set, instead of quietly substituting a default. `level=ludicrous`,
`mode=nonsense`, `dpi=-5`, `fontsize=0` and `combine=maybe` all return `400` with an
explanation. A page number past the end of the document is refused the same way. Error bodies
never contain a traceback or a file path.

**Blank is not a default.** Starlette hands an empty form value to FastAPI as absent, so
`Form("medium")` quietly yields `medium` and the validator above never runs: posting
`level=""` returned a medium-compressed file with no hint the value was discarded. A router
dependency now rejects any empty field that carries a real default, naming it and saying to
omit the field instead. `password`, `pages`, `remove` and `html` are exempt, because blank
there genuinely means "not supplied". Watermark `text` is deliberately not exempt: it defaults
to `CONFIDENTIAL`, so a blank value used to stamp a word across a document that nobody typed,
while a single space returned an error.

**Errors stay readable.** A spec listing 4000 missing pages produced a 23 KB error message.
The response now names the first five and counts the rest, and `audit.py` flags any rejection
whose body grows past 600 bytes: an error should never be larger than the answer.

## Tests

```bash
python selfcheck.py     # 83  endpoints, error paths, hardening regressions
python newcheck.py      # 46  the nine newer tools at API level
python paritycheck.py   # 46  watermark image/tile/angle, flatten, strict page specs
python blankcheck.py    # 39  blank form values, capped errors, reverse ranges
python seccheck.py      # 38  page/file caps, metadata, XMP and attachment stripping
python namecheck.py     # 39  filename sanitiser and header encoding (no server needed)
python tlscheck.py      # 15  HSTS follows the connection, posture intact (no server needed)
python seocheck.py      # 21  page indexable, tool output never, no hardcoded host
python contrast.py      # 52  WCAG AA across both themes (no server needed)
python emojicheck.py    # 12  pure-ASCII rule over every byte and the rendered DOM
python uicheck.py       # 122 assets, tokens, a11y, CSP hygiene, tool parity
python designcheck.py   # 24  computed grid, logos, type scale, hover, sticky rail
python headercheck.py   # 27  header centring, wordmark, responsive tracks
python uxcheck.py       # 27  reviewer pass: labels, search intent, keyboard, mobile
python flowcheck.py     # 55  real browser, tool grid to downloaded file
python newflow.py       # 20  the nine newer tools driven through the browser
python wmflow.py        # 22  watermark logo/tiling and flatten through the browser
python deploycheck.py   # 19  the Vercel entry point serves the same app and headers
python vercelcheck.py   # 18  platform config and caps that would fail a build
python hostcheck.py     # 16  no baked-in host; works under any domain
python degradecheck.py  # 13  a tool whose backend is absent disappears from the UI
python countcheck.py    # 22  every count in this table, verified by running them
python livecheck.py     #     HTTP smoke test
python audit.py         #     adversarial sweep, reports findings by severity
```

776 checks total. `selfcheck`, `newcheck`, `paritycheck`, `blankcheck`, `seccheck`,
`namecheck`, `tlscheck`, `seocheck`, `hostcheck`, `contrast`, `emojicheck`, `deploycheck`
and `vercelcheck` run without a server; the rest need it running. Browser tests need
`pip install playwright && playwright install chromium`.

`seccheck.py` is the one that matters most: it hides a known string in page text, document
metadata, the XMP packet, an annotation, a link URI and an embedded attachment, then checks
that Redact removes every copy. The first version of Redact passed on the page text and left
the other five.

`audit.py` is the hostile-user sweep: corrupt and encrypted files, eight filename injection
vectors, twenty-one parameter abuse cases, wrong-shape requests, header posture, and the temp
residue canary. It prints severities rather than asserting, so it stays useful as a report.

## UI

Tool-first, like the converter sites people already know, built on a bento card grid.

**Library** - hero, search, then four colored category sections. Cards are 1x1 with the
popular tool in each category spanning 2x1. Every card carries app-style format logos
(`PDF` red, `DOC` blue, `XLS` green, `PPT` orange, image violet, `ZIP` slate) so you can
read input and output at a glance without parsing the label.

**Workspace** - one tool, two columns. Left: files and settings. Right: a sticky run rail
with a live summary (file count, total size, output format) and the privacy note. Common
options are visible, the rest sit behind *More options*. Choices of three or fewer become a
segmented control instead of a dropdown.

Design direction from the bundled `ui-ux-pro-max` skill: Bento Grid plus Feature-Rich
Showcase. Card radius 20px, 16px gaps, `translateY(-4px)` hover lift, soft layered shadows,
one accent per category. Fonts are a system stack, not a web font, so no request leaves the
page. UX guidance applied from the same skill: progress indicator during work, error messages
with a recovery action, hover feedback on everything clickable.

```
static/index.html   library + workspace views, zero inline styles
static/app.css      tokens, header, hero, bento grid, category hue classes
static/work.css     workspace, dropzone, options, run rail, footer
static/brands.js    format logos (gradient app tiles, namespaced gradient ids)
static/icons.js     line icons
static/tools.js     17 tools, categories, synonym keywords, input filters
static/main.js      routing, grid build, search, upload, run
```

Tokens in `static/app.css`:

| Group | Tokens |
|---|---|
| Spacing | `--s1` 4px to `--s9` 80px |
| Type | `--t1` 11.5px to `--t8` 42px, `--sans`, `--mono` |
| Radius | `--rc` 20 card, `--rt` 16 tile, `--ri` 14, `--rs` 10, `--rf` pill |
| Surface | `--page`, `--card`, `--soft`, `--line`, `--line-2` |
| Ink | `--ink`, `--ink-2`, `--ink-3` |
| Brand | `--br`, `--br-soft`, `--br-ink` |
| Categories | `--c1`/`--c1s` convert, `--c2` organize, `--c3` optimize, `--c4` secure |
| Elevation | `--e1` to `--e4` |

Light by default, dark follows the system preference and persists in `localStorage`.
Grid reflows 4 to 3 to 2 to 1 column; the workspace drops to one column under 980px.

Navigation: `#tool-name` deep links, browser back works, `/` focuses search, `Esc` clears the
search or leaves the workspace, sticky category nav with scroll-spy. Cards are real buttons,
so Tab reaches them and Enter opens them.

Search matches intent, not just labels. Each tool carries synonym keywords, so "smaller"
finds Compress, "combine" finds Merge, "encrypt" finds Protect, and "spreadsheet" finds
PDF to Excel.

Guard rails: wrong file type for the chosen tool is refused by name, oversized batches are
caught before upload, out-of-range numbers are caught client-side before the round trip,
Merge tells you how many more files it needs, required fields block the run with a specific
message, and failures offer *Try again*. Removing the last file restores the empty state.

## Limits

- 100 MB total per request by default. Set `PDFCUY_MAX_MB` to change it; the UI reads the
  real figure from `/api/engines` rather than carrying its own copy, so what is advertised
  and what is enforced cannot drift apart.
- 1500 pages and 50 files per request, 600 pages on Vercel where the function is killed at
  60 seconds. Bytes alone do not bound the work: a 1 MB file can hold thousands of pages,
  and compressing 3000 of them took 86 seconds of CPU. `PDFCUY_MAX_PAGES` overrides it.
- Scanned PDFs have no text layer, so PDF to Word, Excel, Text, Markdown and Redact have
  nothing to work with. They say so rather than returning an empty file. Add Tesseract if
  you need OCR.
- Compression targets raster images; a text-only PDF is already small, and the original is
  returned when compressing would not help.
- Crop uses the crop box, so a few PDFs with an unusual box will refuse a smaller one.
- Sign stamps an image. It is not a cryptographic signature.
- Built-in Excel to PDF: max 2000 rows and 18 columns per sheet, no cell styling.
  Install LibreOffice for full fidelity.

## Deploying

`vercel.json` and `api/index.py` are included. `deploycheck.py` verifies the entry point
serves the same app with the same headers, and `degradecheck.py` drives a real browser
against a server that reports a missing converter, to prove the UI hides what it cannot run.

Push the repository to GitHub and import it at vercel.com. No CLI and no configuration are
needed: `vercel.json` is read on import and the size limit sets itself, because Vercel
defines `VERCEL=1` and the app drops to 4 MB when it sees it. Two things are worth knowing
before you choose that host.

**Vercel caps request bodies at 4.5 MB.** That is a platform limit, not a setting, and one
ordinary phone scan already exceeds it. Anything larger dies on Vercel's own error page
before our code runs, so the app advertises 4 MB there rather than a number it cannot
honour. Override with `PDFCUY_MAX_MB` only if you know the platform allows more.

**Functions are killed at 60 seconds on Hobby.** A page cap the function cannot finish is a
request that gets accepted and then cut off, so the 1500-page limit drops to 600 on Vercel,
which is roughly 17 seconds of work. `PDFCUY_MAX_PAGES` overrides it. `vercelcheck.py`
asserts the cap still fits inside `maxDuration`, so the two cannot drift apart.

**PDF to Word is excluded from that bundle.** `pdf2docx` pulls in OpenCV and NumPy, about
140 MB. `api/requirements.txt` leaves it out, `/api/engines` reports `pdf2docx: false`, and
the interface drops the card instead of offering one that fails after the upload. Install
`pdf2docx` and the tool returns on its own, with no code change.

For the full 100 MB and all 27 tools, run it yourself. It is a plain ASGI app:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 --no-access-log
```

Any container host works: Fly.io, Railway, Render, or a VPS. Install LibreOffice alongside
it and the legacy `.doc`, `.xls` and `.ppt` formats start working too.

### A custom domain

Nothing in the code names a host. There is no absolute `og:url`, no canonical tag and no
baked-in origin, so moving the site is a DNS change and nothing else. In Vercel: project
Settings, Domains, add the name, then point DNS at the records it shows.

Two details that matter once the domain is yours:

- The landing page is indexable. `/api/` is not: every response there carries
  `X-Robots-Tag: noindex, nofollow, noarchive`, and `/robots.txt` disallows it. A converted
  document is the user's, and it has no business in a search index.
- HSTS starts sending itself as soon as the domain serves HTTPS, with a two-year `max-age`
  and `includeSubDomains`. It does **not** claim `preload`. Submitting to the preload list
  is a near-permanent commitment for every subdomain you will ever have, so that is a
  decision for you, not a default. `seocheck.py` and `tlscheck.py` hold both of these.
