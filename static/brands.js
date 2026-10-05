// PDFCUY - file format logos. App-tile style, brand colors, inline SVG.
// Each FMT entry is a getter so every render emits unique gradient ids (no duplicate DOM ids).

let uid = 0;

const tile = (c1, c2, label, labelSize = 9.4) => {
  const g = 'fmtg' + (++uid);
  return `
<svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
  <defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/>
  </linearGradient></defs>
  <path d="M9 7a3 3 0 0 1 3-3h15l12 12v25a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3z" fill="url(#${g})"/>
  <path d="M27 4l12 12H30a3 3 0 0 1-3-3z" fill="#fff" fill-opacity=".34"/>
  <text x="24" y="35" font-family="ui-sans-serif,system-ui,sans-serif" font-size="${labelSize}"
    font-weight="700" letter-spacing=".3" fill="#fff" text-anchor="middle">${label}</text>
</svg>`;
};

const glyph = (c1, c2, inner) => {
  const g = 'fmth' + (++uid);
  return `
<svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
  <defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/>
  </linearGradient></defs>
  <rect x="6" y="6" width="36" height="36" rx="9" fill="url(#${g})"/>
  ${inner}
</svg>`;
};

const IMG_INNER =
  '<rect x="13" y="15" width="22" height="18" rx="3" fill="#fff" fill-opacity=".92"/>' +
  '<circle cx="19.5" cy="21" r="2.2" fill="#6b43d6" fill-opacity=".55"/>' +
  '<path d="M14 31l6-5.5 4 3.4 4-3.4 6 5.5z" fill="#6b43d6" fill-opacity=".55"/>';

const ZIP_INNER =
  '<rect x="20" y="12" width="8" height="24" rx="2" fill="#fff" fill-opacity=".9"/>' +
  '<path d="M22 17h4M22 21h4M22 25h4" stroke="#495260" stroke-width="1.8" stroke-linecap="round"/>';

// Format chips. `logo` is a getter: each read returns fresh markup with a fresh gradient id.
export const FMT = {
  pdf: { label: 'PDF', get logo() { return tile('#f05146', '#d1251b', 'PDF', 9); } },
  word: { label: 'Word', get logo() { return tile('#4b8ddf', '#1d4f99', 'DOC', 9); } },
  excel: { label: 'Excel', get logo() { return tile('#3fc07a', '#0f7a42', 'XLS', 9.4); } },
  ppt: { label: 'PowerPoint', get logo() { return tile('#f08a5d', '#c0381a', 'PPT', 9.4); } },
  txt: { label: 'Text', get logo() { return tile('#8e97a6', '#5b6472', 'TXT', 9.4); } },
  csv: { label: 'CSV', get logo() { return tile('#5bc0b4', '#1c7f78', 'CSV', 9.4); } },
  html: { label: 'Web', get logo() { return tile('#f2a33c', '#c9701a', 'WEB', 9); } },
  any: { label: 'Any file', get logo() { return tile('#9b8ff0', '#5b46c9', 'ANY', 9.4); } },
  office: { label: 'Office', get logo() { return tile('#4b8ddf', '#1d4f99', 'DOC', 9); } },
  jpg: { label: 'Image', get logo() { return glyph('#a98bf5', '#6b43d6', IMG_INNER); } },
  zip: { label: 'ZIP', get logo() { return glyph('#7b8694', '#495260', ZIP_INNER); } },
};
