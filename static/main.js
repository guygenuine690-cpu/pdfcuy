import { I } from './icons.js';
import { FMT } from './brands.js';
import { TOOLS, CATS, acceptFor, inputLabel, fits, extLogoKey, EXTRA_INPUT, FILE_OPTIONAL }
  from './tools.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (m) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const size = (n) => n < 1024 ? `${n} B`
  : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;

// Starts at the documented default and is corrected by /api/engines once that
// answers. The server owns the real figure: a platform in front of it may cap
// bodies far lower, and a UI that advertises its own number would be lying.
let MAX_MB = 100;
let MAX = MAX_MB * 1024 * 1024;
let files = [], cur = null, busy = false, adv = false, extraFile = null;

// ========== theme ==========
function setTheme(t, save) {
  document.documentElement.dataset.theme = t;
  $('theme').innerHTML = t === 'light' ? I.moon : I.sun;
  $('theme').setAttribute('aria-label',
    t === 'light' ? 'Switch to dark theme' : 'Switch to light theme');
  if (save) try { localStorage.setItem('pdfcuy-theme', t); } catch {}
}

// ========== library ==========
const catIndex = (id) => CATS.findIndex((c) => c.id === id) + 1;

function toolCard(key) {
  const t = TOOLS[key];
  const chip = (k) => `<span class="lg">${FMT[k].logo}</span>`;
  const from = t.from.map(chip).join('');
  return `<button class="tool k${catIndex(t.cat)}${t.feat ? ' feat' : ''}"
      data-k="${key}" data-cat="${t.cat}">
    ${t.feat ? '<span class="badge">Popular</span>' : ''}
    <span class="tile">${t.ic}</span>
    <h3>${esc(t.t)}</h3>
    <p>${esc(t.d)}</p>
    <span class="flow">
      ${from}<span class="ar">${I.arrow}</span>${chip(t.to)}
      <span class="tag">${esc(FMT[t.to].label)}</span>
    </span>
  </button>`;
}

// A tool whose backend is missing must not appear at all. Offering a card that
// always answers 501 is worse than not offering it: the user picks a file,
// waits, and only then finds out. Emptied by /api/engines when the converter
// is absent, which is the case on deployments that cannot carry OpenCV.
const OFF = new Set();
const listed = (k) => !OFF.has(k);

function buildLibrary() {
  $('sections').innerHTML = CATS.map((c, i) => {
    const keys = Object.keys(TOOLS).filter((k) => TOOLS[k].cat === c.id && listed(k));
    return `<section class="sec k${i + 1}" id="cat-${c.id}">
      <div class="shead">
        <span class="sic" aria-hidden="true">${c.ic}</span>
        <span class="st"><h2>${esc(c.n)}</h2><p>${esc(c.d)}</p></span>
        <span class="cnt">${keys.length} tools</span>
      </div>
      <div class="grid">${keys.map(toolCard).join('')}</div>
    </section>`;
  }).join('');

  $('tnav').innerHTML = CATS.map((c) =>
    `<a href="#cat-${c.id}" data-cat="${c.id}">${esc(c.n)}</a>`).join('');

  $('trust').innerHTML = [
    'Files never touch disk', 'No account needed', 'No cookies or analytics',
  ].map((s) => `<span>${I.check}${esc(s)}</span>`).join('');

  const link = (k) => `<li><a href="#" data-open="${k}">${esc(TOOLS[k].t)}</a></li>`;
  $('fconvert').innerHTML = Object.keys(TOOLS).filter((k) => TOOLS[k].cat === 'convert' && listed(k))
    .slice(0, 5).map(link).join('');
  $('fedit').innerHTML = Object.keys(TOOLS).filter((k) => TOOLS[k].cat === 'edit' && listed(k))
    .map(link).join('');
}

function filter(term) {
  const q = term.trim().toLowerCase();
  let shown = 0;
  for (const sec of document.querySelectorAll('.sec')) {
    const cnt = sec.querySelector('.cnt');
    if (!cnt) continue;                     // the no-results block has no badge
    let n = 0;
    for (const card of sec.querySelectorAll('.tool')) {
      const t = TOOLS[card.dataset.k];
      const hay = `${t.t} ${t.d} ${t.kw || ''} ${t.from.join(' ')} ${t.to} ${t.cat}`.toLowerCase();
      const hit = !q || hay.includes(q);
      card.hidden = !hit;
      if (hit) n++;
    }
    sec.hidden = n === 0;
    cnt.textContent = `${n} tool${n === 1 ? '' : 's'}`;
    shown += n;
  }
  let none = $('noresult');
  if (!shown) {
    if (!none) {
      none = document.createElement('div');
      none.id = 'noresult';
      none.className = 'sec';
      none.innerHTML = `<div class="grid"><div class="empty">
        <span class="eic">${I.search}</span>
        <b>No tool matches that</b>
        <span>Try "merge", "password", "excel" or clear the search.</span></div></div>`;
      $('sections').append(none);
    }
    none.hidden = false;
  } else if (none) none.hidden = true;
}

// ========== workspace ==========
function openTool(key, push = true) {
  cur = key; files = []; adv = false; busy = false; extraFile = null;
  const t = TOOLS[key];
  const i = catIndex(t.cat);
  const ws = $('workspace');
  ws.classList.remove('k1', 'k2', 'k3', 'k4');
  ws.classList.add('k' + i);

  $('wtile').innerHTML = t.ic;
  $('wtitle').textContent = t.t;
  $('wdesc').textContent = t.d;
  $('crumbcat').textContent = CATS[i - 1].n;
  $('crumbnow').textContent = t.t;
  $('droptitle').textContent = t.multi ? 'Drop your files here' : 'Drop your file here';
  $('dropsub').textContent = FILE_OPTIONAL.has(key)
    ? `${inputLabel(key)}, or skip this and paste HTML below`
    : `${inputLabel(key)}${t.needs ? `, at least ${t.needs}` : ''} - up to ${MAX_MB} MB in total`;
  $('picker').accept = acceptFor(key);
  $('picker').multiple = !!t.multi;

  $('accepts').innerHTML = t.from.map((f) =>
    `<span class="lg">${FMT[f].logo}</span>`).join('') +
    `<em>to ${esc(FMT[t.to].label)}</em>`;

  $('privlist').innerHTML = [
    'Held in RAM, never written to disk',
    'Discarded as soon as you download',
    'No request logging on the server',
  ].map((s) => `<li>${I.check}<span>${esc(s)}</span></li>`).join('');

  renderOpts();
  drawFiles();
  note('');
  document.title = `${t.t} - PDFCUY`;
  $('library').hidden = true;
  ws.hidden = false;
  if (push) history.pushState({ tool: key }, '', '#' + key);
  scrollTo({ top: 0, behavior: 'instant' });
}

function goLibrary(push = true) {
  cur = null; files = [];
  $('workspace').hidden = true;
  $('library').hidden = false;
  document.title = 'PDFCUY - PDF & Office Tools That Store Nothing';
  if (push) history.pushState({}, '', location.pathname);
}

function visibleOpts() {
  const t = TOOLS[cur];
  // onlyExtra / notExtra follow the onlyMulti precedent: hide a setting that
  // cannot apply yet. Showing "Logo width" with no logo attached, or "Font
  // size" once a logo has replaced the text, invites someone to tune a value
  // that will be ignored.
  return (t.opts || []).filter((o) => !(o.onlyMulti && files.length < 2))
    .filter((o) => !(o.onlyExtra && !extraFile))
    .filter((o) => !(o.notExtra && extraFile));
}

function renderOpts() {
  const all = visibleOpts();
  const main = all.filter((o) => !o.adv);
  const extra = all.filter((o) => o.adv);
  const show = adv ? [...main, ...extra] : main;
  $('optpanel').hidden = !all.length;
  if (!all.length) return;

  $('opts').className = 'opts' + (show.filter((o) => !o.seg).length > 1 ? ' two' : '');
  $('opts').innerHTML = show.map((o) => {
    const id = 'o_' + o.k;
    let ctrl;
    if (o.seg) {
      ctrl = `<div class="seg" role="group" aria-label="${esc(o.l)}" data-seg="${o.k}">
        ${o.o.map(([v, l]) => `<button type="button" data-v="${v}"
          aria-pressed="${v === o.v}">${esc(l)}</button>`).join('')}
        <input type="hidden" id="${id}" value="${o.v}"></div>`;
    } else if (o.type === 'textarea') {
      ctrl = `<textarea id="${id}" rows="4" placeholder="${esc(o.ph || '')}"
        spellcheck="false">${esc(o.v ?? '')}</textarea>`;
    } else if (o.type === 'select') {
      ctrl = `<select id="${id}">${o.o.map(([v, l]) =>
        `<option value="${v}"${v === o.v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    } else {
      ctrl = `<input id="${id}" type="${o.type || 'text'}" value="${esc(o.v ?? '')}"
        placeholder="${esc(o.ph || '')}" ${o.min != null ? `min="${o.min}"` : ''}
        ${o.max != null ? `max="${o.max}"` : ''} ${o.step ? `step="${o.step}"` : ''}
        ${o.type === 'password' ? 'autocomplete="off" spellcheck="false"' : ''}>`;
    }
    return `<div class="f"><label class="lb" for="${id}">${esc(o.l)}${
      o.req ? '<i class="rq" title="Required">*</i>' : ''}</label>${ctrl}${
      o.hint ? `<span class="hint">${esc(o.hint)}</span>` : ''}</div>`;
  }).join('');

  $('advbtn').hidden = !extra.length || adv;
  $('advbtn').setAttribute('aria-expanded', String(adv));
  $('advtxt').textContent = `More options (${extra.length})`;
}

function drawFiles() {
  const t = TOOLS[cur], n = files.length;
  $('dropwrap').hidden = n > 0;
  $('addmore').hidden = !(n > 0 && t.multi);
  $('fcount').textContent = n ? `${n} file${n === 1 ? '' : 's'} - ${size(total())}` : '';
  drawExtra();

  $('flist').innerHTML = files.map((f, i) => {
    const show = t.multi && n > 1;
    return `<li>
      ${show ? `<span class="ord">${i + 1}</span>` : ''}
      <span class="lg">${FMT[extLogoKey(f.name)].logo}</span>
      <span class="fi"><span class="fn">${esc(f.name)}</span>
        <span class="fm">${size(f.size)}</span></span>
      <span class="rowbtns">
        ${show ? `<button class="mini" data-mv="${i}" data-d="-1" ${i === 0 ? 'disabled' : ''}
          aria-label="Move ${esc(f.name)} up">${I.up}</button>
        <button class="mini" data-mv="${i}" data-d="1" ${i === n - 1 ? 'disabled' : ''}
          aria-label="Move ${esc(f.name)} down">${I.down}</button>` : ''}
        <button class="mini dg" data-rm="${i}" aria-label="Remove ${esc(f.name)}">${I.x}</button>
      </span></li>`;
  }).join('');

  drawSummary();
}

const total = () => files.reduce((s, f) => s + f.size, 0);

// Some tools need a second, different file (Sign takes the signature image).
function drawExtra() {
  const spec = EXTRA_INPUT[cur];
  const box = $('extrawrap');
  if (!spec) { box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  const have = extraFile;
  box.innerHTML = `<label class="lb" for="xpick">${esc(spec.label)}
      ${spec.optional ? '' : '<i class="rq" title="Required">*</i>'}</label>
    ${spec.hint ? `<span class="hint">${esc(spec.hint)}</span>` : ''}
    ${have ? `<div class="xrow"><span class="lg">${FMT[extLogoKey(have.name)].logo}</span>
        <span class="fi"><span class="fn">${esc(have.name)}</span>
        <span class="fm">${size(have.size)}</span></span>
        <button class="mini dg" id="xrm" type="button"
          aria-label="Remove ${esc(have.name)}">${I.x}</button></div>`
      : `<button class="xbtn" id="xbtn" type="button">${I.plus}Choose image</button>`}
    <input type="file" id="xpick" accept="${spec.accept}" hidden>`;
  $('xpick').onchange = (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (!f) return;
    if (!/\.(png|jpe?g)$/i.test(f.name)) {
      return note(`The ${spec.label.toLowerCase()} must be a PNG or JPG image.`, 'e');
    }
    if (f.size === 0) return note('That image is empty. Pick another one.', 'e');
    extraFile = f;
    note('');
    renderOpts();
    drawFiles();
  };
  $('xbtn')?.addEventListener('click', () => $('xpick').click());
  $('xrm')?.addEventListener('click', () => { extraFile = null; renderOpts(); drawFiles(); });
}

function drawSummary() {
  const t = TOOLS[cur], n = files.length;
  const need = FILE_OPTIONAL.has(cur) ? 0 : (t.needs || 1);
  $('sum').innerHTML = `
    <div class="sumrow"><span class="k">Files</span>
      <span class="v">${n || '-'}</span></div>
    <div class="sumrow"><span class="k">Total size</span>
      <span class="v">${n ? size(total()) : '-'}</span></div>
    <div class="sumrow"><span class="k">You get</span>
      <span class="v out"><span class="lg">${FMT[t.to].logo}</span>${esc(FMT[t.to].label)}</span></div>`;

  const xs = EXTRA_INPUT[cur];
  const needExtra = xs && !xs.optional && !extraFile;
  const ready = n >= need && !needExtra && !busy;
  $('go').disabled = !ready;
  $('gotxt').textContent = busy ? 'Working...'
    : needExtra ? `Add a ${EXTRA_INPUT[cur].label.toLowerCase()}`
    : n < need ? (need > 1 ? `Add ${need - n} more file${need - n === 1 ? '' : 's'}` : 'Choose a file')
    : t.t;
  $('goic').innerHTML = busy ? `<span class="spin">${I.loader}</span>` : I.bolt;
}

function note(text, kind = 'i', retry = false) {
  const w = $('notewrap');
  if (!text) { w.innerHTML = ''; return; }
  const ic = { s: I.check, e: I.alert, w: I.alert, i: I.info }[kind];
  w.innerHTML = `<div class="note ${kind}">${ic}<span>${esc(text)}${
    retry ? '<button class="again" type="button" id="retry">Try again</button>' : ''}</span></div>`;
}

// ========== files in ==========
function addFiles(incoming) {
  const t = TOOLS[cur];
  const list = [...incoming];
  const empty = list.filter((f) => f.size === 0);
  const wrong = list.filter((f) => f.size > 0 && !fits(cur, f.name));
  let keep = list.filter((f) => f.size > 0 && fits(cur, f.name));

  if (!t.multi) keep = keep.slice(0, 1);
  const next = t.multi ? [...files, ...keep] : keep;

  const sum = next.reduce((s, f) => s + f.size, 0);
  if (sum > MAX) {
    return note(`That would be ${size(sum)}, over the ${MAX_MB} MB limit. Remove a file or compress it first.`, 'e');
  }
  if (!next.length) {
    if (wrong.length) return note(`${TOOLS[cur].t} needs ${inputLabel(cur).toLowerCase()}. "${wrong[0].name}" is not one.`, 'e');
    if (empty.length) return note('That file is empty. Pick another one.', 'e');
    return;
  }

  files = next;
  const skipped = wrong.length + empty.length;
  note(skipped ? `Added ${keep.length}, skipped ${skipped} that this tool cannot read.` : '',
    skipped ? 'w' : 'i');
  renderOpts();
  drawFiles();
}

// ========== run ==========
async function run() {
  const t = TOOLS[cur];
  const need = FILE_OPTIONAL.has(cur) ? 0 : (t.needs || 1);
  if (busy || files.length < need) return;
  const xspec = EXTRA_INPUT[cur];
  if (xspec && !xspec.optional && !extraFile) {
    return note(`${xspec.label} is required before this can run.`, 'e');
  }
  const fd = new FormData();
  files.forEach((f) => fd.append(t.multi ? 'files' : 'file', f, f.name));
  if (extraFile) fd.append(EXTRA_INPUT[cur].field, extraFile, extraFile.name);

  for (const o of visibleOpts()) {
    const el = $('o_' + o.k);
    if (!el) continue;
    const v = (el.value || '').trim();
    if (o.req && !v) {
      el.focus();
      return note(`${o.l} is required before this can run.`, 'e');
    }
    // The server rejects out-of-range numbers, so catch them here first.
    if (v !== '' && o.type === 'number') {
      const n = Number(v);
      if (!Number.isFinite(n) || (o.min != null && n < o.min) || (o.max != null && n > o.max)) {
        el.focus();
        el.select?.();
        return note(`${o.l} must be between ${o.min} and ${o.max}. You entered ${v}.`, 'e');
      }
    }
    if (v !== '') fd.append(o.k, v);
  }

  busy = true; drawSummary();
  $('bar').hidden = false;
  note('Processing in memory. Nothing is being written to disk.');

  try {
    const r = await fetch('/api/' + cur, { method: 'POST', body: fd });
    if (!r.ok) {
      let msg = `The server returned status ${r.status}.`;
      try {
        const j = await r.json();
        if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {}
      throw new Error(msg);
    }
    const blob = await r.blob();
    const name = (r.headers.get('Content-Disposition') || '')
      .match(/filename="?([^";]+)"?/)?.[1] || 'result';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; a.rel = 'noopener';
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    note(`Saved ${name} (${size(blob.size)}) to your downloads. The server copy is already gone.`, 's');
  } catch (err) {
    note(err.message || 'Could not reach the server. Check your connection, then try again.', 'e', true);
  } finally {
    busy = false; $('bar').hidden = true; drawSummary();
  }
}

// ========== wiring ==========
function init() {
  $('mark').innerHTML = I.mark;
  $('searchic').innerHTML = I.search;
  $('backic').innerHTML = I.back;
  $('dropic').innerHTML = I.upload;
  $('ctaic').innerHTML = I.folder;
  $('addic').innerHTML = I.plus;
  $('advic').innerHTML = I.plus;
  $('fphic').innerHTML = I.stack;
  $('ophic').innerHTML = I.sliders;
  $('rphic').innerHTML = I.bolt;
  $('privic').innerHTML = I.shield;
  $('kick').insertAdjacentHTML('afterbegin', I.shield);

  let saved = null;
  try { saved = localStorage.getItem('pdfcuy-theme'); } catch {}
  setTheme(saved || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  $('theme').onclick = () =>
    setTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light', true);

  buildLibrary();

  $('sections').onclick = (e) => {
    const card = e.target.closest('.tool');
    if (card) openTool(card.dataset.k);
  };
  document.querySelector('footer').onclick = (e) => {
    const a = e.target.closest('[data-open]');
    if (a) { e.preventDefault(); openTool(a.dataset.open); }
  };
  $('home').onclick = (e) => { e.preventDefault(); goLibrary(); };
  $('back').onclick = () => goLibrary();

  $('q').oninput = (e) => filter(e.target.value);
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      if ($('library').hidden) return;
      e.preventDefault(); $('q').focus();
    }
    if (e.key === 'Escape') {
      if (document.activeElement === $('q') && $('q').value) { $('q').value = ''; filter(''); }
      else if (!$('workspace').hidden && !busy) goLibrary();
    }
  });

  const drop = $('drop');
  drop.onclick = () => $('picker').click();
  $('addmore').onclick = () => $('picker').click();
  for (const ev of ['dragover', 'dragenter']) {
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); });
  }
  for (const ev of ['dragleave', 'dragend']) {
    drop.addEventListener(ev, () => drop.classList.remove('over'));
  }
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files);
  });
  $('picker').onchange = (e) => { addFiles(e.target.files); e.target.value = ''; };

  $('flist').onclick = (e) => {
    const rm = e.target.closest('[data-rm]'), mv = e.target.closest('[data-mv]');
    if (rm) {
      files.splice(+rm.dataset.rm, 1);
      note(''); renderOpts(); drawFiles();
    } else if (mv) {
      const i = +mv.dataset.mv, j = i + +mv.dataset.d;
      if (j >= 0 && j < files.length) {
        [files[i], files[j]] = [files[j], files[i]];
        drawFiles();
      }
    }
  };

  $('opts').onclick = (e) => {
    const b = e.target.closest('.seg button');
    if (!b) return;
    const box = b.closest('.seg');
    box.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    box.querySelector('input').value = b.dataset.v;
  };
  $('advbtn').onclick = () => { adv = true; renderOpts(); };
  $('go').onclick = run;
  $('notewrap').onclick = (e) => { if (e.target.id === 'retry') run(); };

  // scroll-spy on the category nav
  const links = [...$('tnav').querySelectorAll('a')];
  const spy = new IntersectionObserver((rows) => {
    for (const r of rows) {
      if (!r.isIntersecting) continue;
      const id = r.target.id.replace('cat-', '');
      links.forEach((a) => a.classList.toggle('on', a.dataset.cat === id));
    }
  }, { rootMargin: '-84px 0px -70% 0px' });
  document.querySelectorAll('.sec').forEach((s) => spy.observe(s));

  addEventListener('popstate', () => {
    const k = location.hash.slice(1);
    if (TOOLS[k] && listed(k)) openTool(k, false); else goLibrary(false);
  });

  fetch('/api/engines').then((r) => r.json()).then((e) => {
    if (e.maxMb > 0) {
      MAX_MB = e.maxMb;
      MAX = MAX_MB * 1024 * 1024;
      const cap = document.getElementById('fmax');
      if (cap) cap.textContent = `${MAX_MB} MB`;
    }
    // Drop tools the server cannot run, then rebuild so the cards, the footer
    // links and the section counts all agree.
    if (e.pdf2docx === false) OFF.add('pdf-to-docx');
    if (OFF.size) {
      buildLibrary();
      if (cur && !listed(cur)) { goLibrary(false); }
    }
    if (cur && listed(cur)) openTool(cur, false);  // redraw with the real figure
    const pill = $('engine');
    pill.innerHTML = `<span class="dot"></span><span>${
      e.libreoffice ? 'LibreOffice engine' : 'In-memory engine'}</span>`;
    pill.title = e.libreoffice
      ? 'LibreOffice found: every format supported'
      : 'Built-in engine: modern Office formats supported';
    if (!e.libreoffice) $('flegacy').hidden = false;
  }).catch(() => {});

  const k = location.hash.slice(1);
  if (TOOLS[k] && listed(k)) openTool(k, false);
}

init();
