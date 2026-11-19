'use strict';
// Everything from the data (owner names, legal descriptions...) goes in via textContent /
// text nodes, never as HTML.

const $ = (sel) => document.querySelector(sel);

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return e;
}

const usd = (v) => (v === null || v === undefined || v === '') ? '–'
  : (v < 0 ? '-$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
const bid = (v) => (v === null || v === undefined) ? '–' : v <= 0 ? 'none' : usd(v);
const num = (v, d = 2) => (v === null || v === undefined) ? '–' : (+v).toLocaleString('en-US', { maximumFractionDigits: d });
const pct = (v) => (v === null || v === undefined) ? '–' : Math.round(v * 100) + '%';
const yn = (v) => v === true ? 'Yes' : v === false ? 'No' : '–';
const txt = (v) => (v === null || v === undefined || v === '') ? '–' : String(v);

const CATS = [
  ['pass', 'Pass'], ['review', 'Review'], ['needs', 'Needs data'], ['fail', 'Failed'],
];
const CAT_LABEL = { pass: 'PASS', review: 'REVIEW', needs: 'NEEDS DATA', fail: 'FAIL' };

const state = {
  parcels: [], minScore: 40, selected: null, loaded: false,
  filters: { q: '', county: '', strategy: '', maxbid: '', cats: new Set(['pass', 'review', 'needs']) },
  sort: { key: 'score', dir: -1 },
};

// A failed hard check always shows as failed, even if we also lack value data.
const cat = (p) => p.status === 'FAIL' ? 'fail' : (p.needs_data ? 'needs' : (p.status || 'review').toLowerCase());
const profitOf = (p) => p.strategy === 'rehab' ? p.est_profit : p.est_equity;
const nameOf = (p) => p.address || p.legal_description || p.parcel_id;

const COLS = [
  ['score', 'Score', (p) => p.deal_score, 'num'],
  ['status', 'Status', (p) => cat(p), ''],
  ['name', 'Property', (p) => nameOf(p).toLowerCase(), ''],
  ['county', 'County', (p) => p.county, ''],
  ['strategy', 'Type', (p) => p.strategy, ''],
  ['opening', 'Opening bid', (p) => p.opening_bid, 'num'],
  ['ideal', 'Ideal bid', (p) => p.ideal_bid, 'num'],
  ['max', 'Max bid', (p) => p.max_bid, 'num'],
  ['profit', 'Est. profit', (p) => profitOf(p), 'num'],
  ['avail', 'Available', (p) => p.available_date, ''],
];

async function load() {
  $('#subtitle').textContent = 'Loading…';
  let data;
  try {
    const r = await fetch('api/parcels', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    data = await r.json();
  } catch (e) {
    $('#subtitle').textContent = 'Could not load the properties: ' + e.message;
    return;
  }
  state.parcels = data.parcels;
  state.minScore = data.min_score;
  state.loaded = true;
  if (state.selected && !state.parcels.some((p) => p.key === state.selected)) state.selected = null;
  renderAll();
}

function visible() {
  const f = state.filters;
  const q = f.q.trim().toLowerCase();
  const maxbid = f.maxbid === '' ? null : Number(f.maxbid);
  const rows = state.parcels.filter((p) => {
    if (!f.cats.has(cat(p))) return false;
    if (f.county && p.county !== f.county) return false;
    if (f.strategy && p.strategy !== f.strategy) return false;
    if (maxbid !== null && !(p.opening_bid !== null && p.opening_bid <= maxbid)) return false;
    if (q) {
      const hay = [p.address, p.parcel_id, p.owner_name, p.legal_description, p.county, p.case_number]
        .join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const col = COLS.find((c) => c[0] === state.sort.key) || COLS[0];
  const dir = state.sort.dir;
  rows.sort((a, b) => {
    const x = col[2](a), y = col[2](b);
    const xn = x === null || x === undefined || x === '', yn_ = y === null || y === undefined || y === '';
    if (xn && yn_) return 0;
    if (xn) return 1;           // empty values always last
    if (yn_) return -1;
    const c = x < y ? -1 : x > y ? 1 : 0;
    if (c !== 0) return c * dir;
    // ties: cheaper opening bid first
    return (a.opening_bid ?? Infinity) - (b.opening_bid ?? Infinity);
  });
  return rows;
}

function renderTiles() {
  const P = state.parcels;
  const worth = P.filter((p) => (p.status === 'PASS' || p.status === 'REVIEW') && (p.deal_score || 0) >= state.minScore).length;
  const count = (c) => P.filter((p) => cat(p) === c).length;
  const tiles = [
    ['Worth a look', worth], ['Pass', count('pass')], ['Review', count('review')],
    ['Needs data', count('needs')], ['Failed', count('fail')], ['New', P.filter((p) => p.is_new).length],
  ];
  $('#tiles').replaceChildren(...tiles.map(([label, n]) => h('div', { class: 'tile' }, h('b', {}, n), h('span', {}, label))));
}

function renderFilters() {
  const counties = [...new Set(state.parcels.map((p) => p.county))].sort();
  const sel = $('#county');
  const cur = state.filters.county;
  sel.replaceChildren(h('option', { value: '' }, 'All'), ...counties.map((c) => h('option', { value: c }, c || '(none)')));
  sel.value = counties.includes(cur) ? cur : '';
  state.filters.county = sel.value;

  const counts = {};
  for (const p of state.parcels) counts[cat(p)] = (counts[cat(p)] || 0) + 1;
  $('#chips').replaceChildren(...CATS.map(([id, label]) => h('button', {
    class: 'chip', type: 'button', 'aria-pressed': String(state.filters.cats.has(id)),
    onclick: () => { toggle(state.filters.cats, id); renderAll(); },
  }, `${label} (${counts[id] || 0})`)));
}

function toggle(set, v) { set.has(v) ? set.delete(v) : set.add(v); }

function renderTable() {
  const rows = visible();
  const LIMIT = 500;
  $('#thead').replaceChildren(h('tr', {}, ...COLS.map(([key, label, , cls]) => h('th', {
    class: cls, scope: 'col', tabindex: 0,
    'aria-sort': state.sort.key === key ? (state.sort.dir === 1 ? 'ascending' : 'descending') : 'none',
    onclick: () => sortBy(key),
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(key); } },
  }, label))));

  $('#tbody').replaceChildren(...rows.slice(0, LIMIT).map((p) => {
    const c = cat(p);
    return h('tr', {
      tabindex: 0, 'aria-selected': String(state.selected === p.key),
      onclick: () => select(p.key),
      onkeydown: (e) => { if (e.key === 'Enter') select(p.key); },
    },
      h('td', { class: 'num' }, p.needs_data ? h('span', { class: 'dim' }, '–') : num(p.deal_score, 1)),
      h('td', {}, h('span', { class: 'badge ' + c }, CAT_LABEL[c]), p.is_new && h('span', { class: 'badge new' }, 'NEW')),
      h('td', { class: 'name' }, nameOf(p), h('small', {}, p.address ? p.parcel_id : (p.owner_name || ''))),
      h('td', {}, p.county),
      h('td', {}, p.strategy === 'rehab' ? 'House' : 'Land'),
      h('td', { class: 'num' }, usd(p.opening_bid)),
      h('td', { class: 'num' }, bid(p.ideal_bid)),
      h('td', { class: 'num' }, bid(p.max_bid)),
      h('td', { class: 'num' }, usd(profitOf(p))),
      h('td', {}, txt(p.available_date)));
  }));

  const empty = $('#empty');
  empty.hidden = rows.length > 0;
  if (!rows.length) {
    empty.textContent = state.parcels.length
      ? 'No properties match these filters. Try turning on "Needs data" or "Failed", or clearing the search.'
      : 'No properties yet. Run `taxdeed auto` to download and screen your lists, then reload this page.';
  }
  const shown = Math.min(rows.length, LIMIT);
  $('#subtitle').textContent = state.loaded
    ? `${state.parcels.length} properties in the database · showing ${shown}${rows.length > LIMIT ? ` of ${rows.length} (narrow the filters to see the rest)` : ''}`
    : 'Loading…';
}

function sortBy(key) {
  state.sort = state.sort.key === key ? { key, dir: -state.sort.dir } : { key, dir: key === 'name' || key === 'county' || key === 'status' ? 1 : -1 };
  renderTable();
}

function select(key) {
  state.selected = key;
  renderTable();
  renderDetail();
  if (window.matchMedia('(max-width: 1050px)').matches) $('#detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function linksFor(p) {
  const links = [];
  if (p.lat !== null && p.lon !== null) links.push(['Map', `https://www.google.com/maps?q=${p.lat},${p.lon}`]);
  else if (p.address) links.push(['Map', 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(`${p.address}, ${p.county} County, ${p.state}`)]);
  else links.push(['Search legal description', 'https://www.google.com/search?q=' + encodeURIComponent(`${p.county} County ${p.state} parcel ${p.parcel_id}`)]);
  // Same link pattern Putnam's own list uses for every parcel.
  if (p.county === 'Putnam') links.push(['Putnam property map (GIS)', 'https://gisweb.putnam-fl.com/PropertyAppraiserPublicMap/?find=' + encodeURIComponent(p.parcel_id)]);
  return links;
}

function list(items, cls) {
  return items.length ? h('ul', { class: 'list ' + cls }, items.map((t) => h('li', {}, t))) : null;
}

function renderDetail() {
  const box = $('#detail');
  const p = state.parcels.find((x) => x.key === state.selected);
  if (!p) {
    box.replaceChildren(h('p', { class: 'hint' }, 'Select a property to see its ideal bid, max bid, and why it passed or failed. You can also enter values you have researched (value, ARV, lot size) and it re-scores right away.'));
    return;
  }
  const c = cat(p);
  const facts = [
    ['Type', p.strategy === 'rehab' ? 'House to renovate' : 'Vacant land'],
    ['Parcel', p.parcel_id], ['Case no.', p.case_number], ['Owner', p.owner_name],
    ['Legal description', p.legal_description], ['Sale date', p.sale_date], ['Available to buy', p.available_date],
    ['Lot size (acres)', p.lot_acres === null ? null : num(p.lot_acres)], ['Lot width (ft)', p.lot_width_ft === null ? null : num(p.lot_width_ft, 0)],
    ['Zoning', p.zoning], ['Flood zone', p.flood_zone], ['Wetlands', p.wetlands === null ? null : (p.wetlands ? 'Mapped: ' + p.wetland_types : 'None mapped')],
    ['Slope', p.slope_pct === null ? null : p.slope_pct + '%'], ['Road access', p.road_frontage === null ? null : yn(p.road_frontage)],
    ['Assessed value', usd(p.assessed_value)], ['Value used', usd(p.est_market_value)],
    ...(p.strategy === 'rehab' ? [
      ['Building (sq ft)', p.building_sqft === null ? null : num(p.building_sqft, 0)], ['Year built', p.year_built === null ? null : Math.round(p.year_built)],
      ['Condition', p.condition], ['Occupied', yn(p.occupied)], ['Renovation scope', p.rehab_tier], ['Est. repairs', usd(p.est_rehab_cost)],
      ['After-repair value', usd(p.est_arv)], ['ROI', pct(p.roi)], ['Rent yield', pct(p.rent_yield)],
    ] : [['Bid ÷ value', pct(p.bid_to_value)]]),
    ['Source', p.source],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== '–');

  box.replaceChildren(
    h('h2', {}, nameOf(p)),
    h('div', {}, h('span', { class: 'badge ' + c }, CAT_LABEL[c]), p.is_new && h('span', { class: 'badge new' }, 'NEW'),
      h('span', { class: 'dim' }, `  ${p.county} County${p.needs_data ? '' : ' · score ' + num(p.deal_score, 1)}`)),
    h('div', { class: 'prices' },
      h('div', { class: 'price' }, h('span', {}, 'Opening bid'), h('b', {}, usd(p.opening_bid))),
      h('div', { class: 'price ideal' }, h('span', {}, 'Ideal bid'), h('b', {}, bid(p.ideal_bid))),
      h('div', { class: 'price max' }, h('span', {}, 'Max bid'), h('b', {}, bid(p.max_bid)))),
    (p.ideal_bid !== null && p.ideal_bid <= 0) && h('p', { class: 'hint' }, 'No bid on this one can reach your target: your fixed costs (closing, quiet title) are larger than the room the value leaves. Check those costs in config.yaml if they look too high for a lot this cheap.'),
    p.needs_data && h('p', { class: 'hint' }, 'No value for this property yet, so the ideal and max bid can\'t be worked out. Enter its assessed value (or ARV for a house) below.'),
    p.reasons.length > 0 && h('h3', {}, c === 'fail' ? 'Why it failed' : 'Still to check'),
    list(p.reasons, c === 'fail' ? 'fail' : 'warn'),
    p.red_flags.length > 0 && h('h3', {}, 'Red flags'), list(p.red_flags, 'fail'),
    p.notes.length > 0 && h('h3', {}, 'Notes'), list(p.notes, 'warn'),
    h('h3', {}, 'Links'),
    h('div', { class: 'links' }, linksFor(p).map(([label, href]) => h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, label))),
    h('h3', {}, 'Details'),
    h('dl', { class: 'facts' }, facts.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, String(v))])),
    h('h3', {}, 'Your numbers'),
    editForm(p),
  );
}

const FIELDS = [
  ['assessed_value', 'Assessed / market value ($)', 'num'],
  ['est_arv', 'After-repair value, ARV ($)', 'num'],
  ['lot_acres', 'Lot size (acres)', 'num'],
  ['lot_width_ft', 'Lot width (ft)', 'num'],
  ['building_sqft', 'Building size (sq ft)', 'num'],
  ['year_built', 'Year built', 'num'],
  ['est_rent', 'Monthly rent ($)', 'num'],
  ['zoning', 'Zoning', 'text'],
  ['condition', 'Condition (e.g. Good, Fair, Poor)', 'text'],
  ['road_frontage', 'Touches a public road', 'bool'],
  ['improved', 'Has a building', 'bool'],
  ['occupied', 'Occupied', 'bool'],
];

function editForm(p) {
  const inputs = {};
  const form = h('form', { class: 'edit', novalidate: true });
  for (const [name, label, kind] of FIELDS) {
    let input;
    if (kind === 'bool') {
      input = h('select', { name }, h('option', { value: '' }, 'Unknown'), h('option', { value: 'true' }, 'Yes'), h('option', { value: 'false' }, 'No'));
      input.value = p[name] === true ? 'true' : p[name] === false ? 'false' : '';
    } else {
      input = h('input', { name, type: kind === 'num' ? 'number' : 'text', min: kind === 'num' ? 0 : null, step: kind === 'num' ? 'any' : null, maxlength: kind === 'text' ? 60 : null });
      input.value = p[name] === null || p[name] === undefined ? '' : p[name];
    }
    inputs[name] = [input, kind];
    form.append(h('label', {}, label, input));
  }
  const msg = h('span', { class: 'msg', role: 'status' });
  const save = h('button', { class: 'btn primary', type: 'submit' }, 'Save and re-score');
  form.append(h('div', { class: 'actions' }, save, msg));
  form.append(h('p', { class: 'hint formnote' }, 'Saved to overrides.ui.csv, so a new download never erases what you enter. Leave a box empty to clear it.'));

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const changes = {};
    for (const [name, [input, kind]] of Object.entries(inputs)) {
      const raw = input.value.trim();
      const val = kind === 'bool' ? (raw === '' ? null : raw === 'true') : (raw === '' ? null : (kind === 'num' ? Number(raw) : raw));
      const was = p[name] === undefined || p[name] === '' ? null : p[name];
      if (val !== was) changes[name] = val;
    }
    if (!Object.keys(changes).length) { msg.className = 'msg'; msg.textContent = 'No changes.'; return; }
    save.disabled = true; msg.className = 'msg'; msg.textContent = 'Saving…';
    try {
      const r = await fetch('api/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Taxdeed': '1' },
        body: JSON.stringify({ county: p.county, parcel_id: p.parcel_id, changes }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || 'HTTP ' + r.status);
      const i = state.parcels.findIndex((x) => x.key === data.key);
      if (i >= 0) state.parcels[i] = data;
      renderTiles(); renderFilters(); renderTable(); renderDetail();
      const m = $('#detail .msg');
      if (m) { m.className = 'msg ok'; m.textContent = 'Saved and re-scored.'; }
    } catch (e) {
      msg.className = 'msg err'; msg.textContent = 'Not saved: ' + e.message; save.disabled = false;
    }
  });
  return form;
}

function renderAll() { renderTiles(); renderFilters(); renderTable(); renderDetail(); }

$('#q').addEventListener('input', (e) => { state.filters.q = e.target.value; renderTable(); });
$('#county').addEventListener('change', (e) => { state.filters.county = e.target.value; renderTable(); });
$('#strategy').addEventListener('change', (e) => { state.filters.strategy = e.target.value; renderTable(); });
$('#maxbid').addEventListener('input', (e) => { state.filters.maxbid = e.target.value; renderTable(); });
$('#reload').addEventListener('click', load);

load();
