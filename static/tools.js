import { I } from './icons.js';

const PAGES = 'Leave blank for all pages. Example: 1-3,7,10-';
const PAGES_REQ = 'Example: 1-3,7,10-';
const PW = { k: 'password', l: 'PDF password', type: 'password', ph: 'only if the file is locked', adv: 1 };
const PG = () => ({ k: 'pages', l: 'Pages', ph: 'all pages', hint: PAGES, adv: 1 });

// seg:1 renders a segmented control instead of a dropdown (<=3 choices)
export const TOOLS = {
  'office-to-pdf': {
    t: 'Office to PDF', ic: I.filePdf, cat: 'convert', feat: 1,
    d: 'Turn Word, Excel or PowerPoint files into PDF with the layout intact.',
    kw: 'docx xlsx pptx doc xls ppt save export print layout',
    from: ['word', 'excel', 'ppt'], to: 'pdf', multi: 1,
    opts: [{ k: 'combine', l: 'Several files', type: 'select', v: 'false', seg: 1,
      o: [['false', 'Separate PDFs'], ['true', 'Merge into one']], onlyMulti: 1 }],
  },
  'pdf-to-docx': {
    t: 'PDF to Word', ic: I.word, cat: 'convert',
    d: 'Get an editable .docx with text, headings and tables preserved.',
    kw: 'docx doc editable edit msword writer',
    from: ['pdf'], to: 'word', opts: [PG(), PW],
  },
  'pdf-to-xlsx': {
    t: 'PDF to Excel', ic: I.sheet, cat: 'convert',
    d: 'Detect tables and drop them into spreadsheet rows and columns.',
    kw: 'xlsx xls spreadsheet table rows columns data',
    from: ['pdf'], to: 'excel', opts: [PG(), PW],
  },
  'pdf-to-pptx': {
    t: 'PDF to PowerPoint', ic: I.deck, cat: 'convert',
    d: 'One slide per page, rendered at the quality you pick.',
    kw: 'pptx ppt slides deck presentation keynote',
    from: ['pdf'], to: 'ppt',
    opts: [{ k: 'dpi', l: 'Render quality', type: 'number', v: 120, min: 72, max: 200,
      hint: '72 to 200 DPI', adv: 1 }, PG(), PW],
  },
  'pdf-to-images': {
    t: 'PDF to JPG', ic: I.image, cat: 'convert',
    d: 'Export every page as a PNG or JPG image, bundled in a ZIP.',
    kw: 'jpg jpeg png image picture photo screenshot export render zip',
    from: ['pdf'], to: 'jpg',
    opts: [
      { k: 'fmt', l: 'Image format', type: 'select', v: 'png', seg: 1,
        o: [['png', 'PNG'], ['jpg', 'JPG']] },
      { k: 'dpi', l: 'Resolution', type: 'number', v: 150, min: 36, max: 300,
        hint: '36 to 300 DPI. Higher means larger files.', adv: 1 },
      PG(), PW,
    ],
  },
  'images-to-pdf': {
    t: 'JPG to PDF', ic: I.filePdf, cat: 'convert',
    d: 'Combine photos and scans into a single ordered PDF.',
    kw: 'jpg jpeg png image photo scan combine join album',
    from: ['jpg'], to: 'pdf', multi: 1,
    opts: [
      { k: 'size', l: 'Page size', type: 'select', v: 'fit', seg: 1,
        o: [['fit', 'Match image'], ['a4', 'A4']] },
      { k: 'margin', l: 'Margin', type: 'number', v: 0, min: 0, max: 120,
        hint: 'In points. A4 only.', adv: 1 },
    ],
  },
  convert: {
    t: 'Convert anything', ic: I.swap, cat: 'convert',
    d: 'Name any target format. Needs LibreOffice on the server for exotic ones.',
    kw: 'odt ods odp rtf html csv custom other format change',
    from: ['any'], to: 'any',
    opts: [{ k: 'to', l: 'Target format', req: 1, ph: 'odt, rtf, csv, html',
      hint: 'pdf always works. Others need LibreOffice.' }],
  },
  'html-to-pdf': {
    t: 'HTML to PDF', ic: I.code, cat: 'convert',
    d: 'Paste markup or drop an .html file and get a paginated PDF.',
    kw: 'html htm web page markup webpage site render print',
    from: ['html'], to: 'pdf', optional: 1,
    opts: [
      { k: 'html', l: 'HTML', type: 'textarea', ph: '<h1>Invoice</h1><p>Total: 100</p>',
        hint: 'Or choose a file above. Remote images are not fetched, by design.' },
      { k: 'size', l: 'Page size', type: 'select', v: 'a4', seg: 1,
        o: [['a4', 'A4'], ['letter', 'Letter'], ['legal', 'Legal']] },
    ],
  },
  'pdf-to-markdown': {
    t: 'PDF to Markdown', ic: I.md, cat: 'convert',
    d: 'Export the text as .md, turning bigger type into headings.',
    kw: 'md markdown text notion obsidian plain headings llm',
    from: ['pdf'], to: 'txt', opts: [PG(), PW],
  },

  merge: {
    t: 'Merge PDF', ic: I.merge, cat: 'edit', feat: 1,
    d: 'Join several PDFs into one. Drag the rows to set the final order.',
    kw: 'combine join append concat together one single stitch bind',
    from: ['pdf'], to: 'pdf', multi: 1, needs: 2, opts: [PW],
  },
  split: {
    t: 'Split PDF', ic: I.scissors, cat: 'edit',
    d: 'Pull out the pages you want, or break the file into pieces.',
    kw: 'separate divide extract cut break apart chunk zip single pages',
    from: ['pdf'], to: 'zip',
    opts: [
      { k: 'mode', l: 'Split method', type: 'select', v: 'extract', seg: 1,
        o: [['extract', 'Pick pages'], ['each', 'Every page'], ['ranges', 'By range']] },
      { k: 'pages', l: 'Pages', ph: '1-3,7', hint: 'For ranges, separate with a space: 1-3 4-8' },
      PW,
    ],
  },
  organize: {
    t: 'Organize PDF', ic: I.shuffle, cat: 'edit',
    d: 'Reorder pages and delete the ones you do not need.',
    kw: 'reorder rearrange sort move delete remove page order shuffle',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'pages', l: 'New page order', ph: '3,1,2', hint: 'Blank keeps the current order' },
      { k: 'remove', l: 'Delete pages', ph: '4,9', hint: 'Applied after reordering' },
      PW,
    ],
  },
  rotate: {
    t: 'Rotate PDF', ic: I.rotate, cat: 'edit',
    d: 'Straighten sideways scans. Rotate every page or just a few.',
    kw: 'turn flip sideways upside down landscape portrait orientation straighten scan',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'angle', l: 'Rotation', type: 'select', v: '90', seg: 1,
        o: [['90', 'Right 90'], ['180', '180'], ['270', 'Left 90']] },
      PG(), PW,
    ],
  },
  'remove-pages': {
    t: 'Remove pages', ic: I.trash, cat: 'edit',
    d: 'Delete the pages you list and keep everything else.',
    kw: 'delete drop discard erase cut unwanted blank page',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'pages', l: 'Pages to remove', ph: '2,5,9-11', req: 1, hint: PAGES_REQ },
      PW,
    ],
  },
  'extract-pages': {
    t: 'Extract pages', ic: I.pick, cat: 'edit',
    d: 'Keep only the pages you list, in the order you write them.',
    kw: 'keep select pick subset copy chapter range page',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'pages', l: 'Pages to keep', ph: '1-3,8', req: 1, hint: PAGES_REQ },
      PW,
    ],
  },
  'page-numbers': {
    t: 'Add page numbers', ic: I.hash, cat: 'edit',
    d: 'Stamp numbers in any corner, with a starting value you choose.',
    kw: 'number numbering folio paginate footer header label page',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'position', l: 'Position', type: 'select', v: 'bottom-center',
        o: [['bottom-center', 'Bottom centre'], ['bottom-left', 'Bottom left'],
          ['bottom-right', 'Bottom right'], ['top-center', 'Top centre'],
          ['top-left', 'Top left'], ['top-right', 'Top right']] },
      { k: 'fmt', l: 'Format', type: 'select', v: 'n', seg: 1,
        o: [['n', '1'], ['n_of_total', '1 / 9'], ['page_n', 'Page 1']] },
      { k: 'start', l: 'Start at', type: 'number', v: 1, min: 0, max: 100000, adv: 1 },
      { k: 'fontsize', l: 'Font size', type: 'number', v: 10, min: 6, max: 48, adv: 1 },
      PG(), PW,
    ],
  },
  crop: {
    t: 'Crop PDF', ic: I.crop, cat: 'edit',
    d: 'Trim white margins from any edge. Values are a percentage.',
    kw: 'trim margin edge cut border whitespace resize scan',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'top', l: 'Top %', type: 'number', v: 0, min: 0, max: 45 },
      { k: 'bottom', l: 'Bottom %', type: 'number', v: 0, min: 0, max: 45 },
      { k: 'left', l: 'Left %', type: 'number', v: 0, min: 0, max: 45, adv: 1 },
      { k: 'right', l: 'Right %', type: 'number', v: 0, min: 0, max: 45, adv: 1 },
      PG(), PW,
    ],
  },

  compress: {
    t: 'Compress PDF', ic: I.minimize, cat: 'optimize', feat: 1,
    d: 'Shrink the file size while keeping text crisp. Three strength levels.',
    kw: 'smaller shrink reduce size optimize lighter squeeze email attachment too big mb',
    from: ['pdf'], to: 'pdf',
    opts: [{ k: 'level', l: 'Compression', type: 'select', v: 'medium', seg: 1,
      o: [['low', 'Light'], ['medium', 'Balanced'], ['high', 'Strong']] }, PW],
  },
  'extract-text': {
    t: 'PDF to Text', ic: I.textscan, cat: 'optimize',
    d: 'Pull the raw text out of a PDF as a plain .txt file.',
    kw: 'txt plain copy read words content extract scrape',
    from: ['pdf'], to: 'txt', opts: [PG(), PW],
  },
  'office-text': {
    t: 'Office to Text', ic: I.textscan, cat: 'optimize',
    d: 'Strip formatting from a Word, Excel or PowerPoint file.',
    kw: 'txt plain docx xlsx pptx strip formatting words content',
    from: ['office'], to: 'txt', opts: [],
  },
  repair: {
    t: 'Repair PDF', ic: I.wrench, cat: 'optimize',
    d: 'Rebuild a file that will not open, recovering every readable page.',
    kw: 'fix broken corrupt damaged recover rebuild error wont open',
    from: ['pdf'], to: 'pdf', opts: [PW],
  },
  flatten: {
    t: 'Flatten PDF', ic: I.layers, cat: 'optimize',
    d: 'Make filled form fields and comments permanent so they cannot be changed.',
    kw: 'form field annotation comment highlight permanent lock freeze '
      + 'merge layers read only signature',
    from: ['pdf'], to: 'pdf', opts: [PW],
  },

  protect: {
    t: 'Protect PDF', ic: I.lock, cat: 'secure', feat: 1,
    d: 'Lock the document with AES-256 encryption and your own password.',
    kw: 'password encrypt lock secure private aes restrict confidential',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'new_password', l: 'New password', type: 'password', req: 1,
        hint: 'At least 4 characters. Nobody can recover it for you.' },
      { k: 'allow_print', l: 'Allow printing', type: 'select', v: 'true', seg: 1,
        o: [['true', 'Allow'], ['false', 'Block']], adv: 1 },
      { k: 'password', l: 'Current password', type: 'password', ph: 'if already locked', adv: 1 },
    ],
  },
  unlock: {
    t: 'Unlock PDF', ic: I.unlock, cat: 'secure',
    d: 'Remove a password you already know, so the file opens freely.',
    kw: 'password decrypt remove open unprotect forgot',
    from: ['pdf'], to: 'pdf',
    opts: [{ k: 'password', l: 'Current password', type: 'password', req: 1,
      hint: 'We cannot crack unknown passwords.' }],
  },
  watermark: {
    t: 'Watermark PDF', ic: I.drop, cat: 'secure',
    d: 'Stamp text or your own logo across the pages you choose.',
    kw: 'stamp overlay draft confidential copyright brand text label logo image '
      + 'tile diagonal angle rotate',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'text', l: 'Watermark text', v: 'CONFIDENTIAL', notExtra: 1 },
      { k: 'place', l: 'Position', type: 'select', v: 'center',
        o: [['center', 'Centre'], ['top', 'Top'], ['bottom', 'Bottom'],
          ['top-left', 'Top left'], ['top-right', 'Top right'],
          ['bottom-left', 'Bottom left'], ['bottom-right', 'Bottom right']] },
      { k: 'tile', l: 'Repeat', type: 'select', v: 'off', seg: 1,
        o: [['off', 'Once'], ['on', 'Tile the page']] },
      { k: 'angle', l: 'Angle', type: 'number', v: 0, min: -90, max: 90,
        hint: '45 for a diagonal stamp' },
      { k: 'fontsize', l: 'Font size', type: 'number', v: 48, min: 8, max: 200,
        adv: 1, notExtra: 1 },
      { k: 'width', l: 'Logo size %', type: 'number', v: 40, min: 5, max: 100,
        hint: 'Share of the page width', onlyExtra: 1 },
      { k: 'opacity', l: 'Opacity', type: 'number', v: 0.18, min: 0.03, max: 1, step: 0.01,
        hint: '0.03 to 1.00', adv: 1 },
      PG(), PW,
    ],
  },
  redact: {
    t: 'Redact PDF', ic: I.redact, cat: 'secure', feat: 1,
    d: 'Delete sensitive words for good. The text is removed, not just covered.',
    kw: 'black out censor hide remove sensitive private confidential gdpr erase',
    from: ['pdf'], to: 'pdf',
    opts: [
      { k: 'words', l: 'Words to remove', type: 'textarea', req: 1,
        ph: 'account number\nJane Doe',
        hint: 'One word or phrase per line. Up to 40.' },
      { k: 'match_case', l: 'Matching', type: 'select', v: 'false', seg: 1,
        o: [['false', 'Any case'], ['true', 'Exact case']], adv: 1 },
      PG(), PW,
    ],
  },
  sign: {
    t: 'Sign PDF', ic: I.pen, cat: 'secure',
    d: 'Place a signature image on a page. Upload the PDF, then the signature.',
    kw: 'signature initial stamp autograph image sign contract',
    from: ['pdf'], to: 'pdf', extra: 'image',
    opts: [
      { k: 'corner', l: 'Position', type: 'select', v: 'bottom-right',
        o: [['bottom-right', 'Bottom right'], ['bottom-left', 'Bottom left'],
          ['top-right', 'Top right'], ['top-left', 'Top left']] },
      { k: 'page_no', l: 'Page', type: 'number', v: -1, min: -1, max: 100000,
        hint: 'Leave -1 for the last page', adv: 1 },
      { k: 'width', l: 'Width %', type: 'number', v: 30, min: 5, max: 90, adv: 1 },
      PW,
    ],
  },
};

export const CATS = [
  { id: 'convert', n: 'Convert', ic: I.swap, d: 'Move between PDF, Office and image formats' },
  { id: 'edit', n: 'Organize', ic: I.shuffle, d: 'Merge, split, reorder and rotate pages' },
  { id: 'optimize', n: 'Optimize', ic: I.bolt, d: 'Shrink files and extract their contents' },
  { id: 'secure', n: 'Secure', ic: I.shield, d: 'Passwords, encryption and watermarks' },
];

const OFFICE_EXT = ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'odt', 'ods', 'odp',
  'rtf', 'txt', 'md', 'csv', 'html', 'htm'];
const IMAGE_EXT = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff'];

// What each tool will take, so the picker can filter and we can warn early.
const ACCEPTS = {
  pdf: ['pdf'],
  office: OFFICE_EXT,
  image: IMAGE_EXT,
  html: ['html', 'htm'],
  any: ['pdf', ...OFFICE_EXT, ...IMAGE_EXT],
};
const TOOL_INPUT = {
  'office-to-pdf': 'office', 'office-text': 'office', convert: 'any',
  'images-to-pdf': 'image', 'html-to-pdf': 'html',
};

// Tools that take a second, different file (PDF first, then this).
export const EXTRA_INPUT = {
  sign: { field: 'image', label: 'Signature image', accept: '.png,.jpg,.jpeg' },
  watermark: {
    field: 'image', label: 'Logo image', accept: '.png,.jpg,.jpeg', optional: 1,
    hint: 'Optional. Added instead of the text above.',
  },
};

// Tools that can run with no file at all (HTML to PDF accepts pasted markup).
export const FILE_OPTIONAL = new Set(['html-to-pdf']);

export function acceptFor(key) {
  const grp = TOOL_INPUT[key] || 'pdf';
  return ACCEPTS[grp].map((e) => '.' + e).join(',');
}

export function inputLabel(key) {
  const grp = TOOL_INPUT[key] || 'pdf';
  return { pdf: 'PDF files', office: 'Office or text files', image: 'Images',
    html: 'HTML files', any: 'Any document' }[grp];
}

export function fits(key, name) {
  const ext = (name.split('.').pop() || '').toLowerCase();
  return ACCEPTS[TOOL_INPUT[key] || 'pdf'].includes(ext);
}

export function extLogoKey(name) {
  const e = (name.split('.').pop() || '').toLowerCase();
  if (e === 'pdf') return 'pdf';
  if (['docx', 'doc', 'odt', 'rtf'].includes(e)) return 'word';
  if (['xlsx', 'xls', 'ods'].includes(e)) return 'excel';
  if (['pptx', 'ppt', 'odp'].includes(e)) return 'ppt';
  if (['csv'].includes(e)) return 'csv';
  if (['html', 'htm'].includes(e)) return 'html';
  if (['txt', 'md'].includes(e)) return 'txt';
  if (IMAGE_EXT.includes(e)) return 'jpg';
  return 'any';
}
