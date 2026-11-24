/* Home screen editor: choose the cards, drag them, resize them, change the grid. ES5 on purpose.
   Landscape: drag a card to move it (dropping on a card of the same size swaps them), drag its corner to resize.
   Portrait: the cards stack in reading order, so each card has arrows to move it up or down.
   The layout is saved on this phone ("dh_home"); the PC's own layout is used until this is changed. */
(function () {
  'use strict';
  var D = window.DH, UI = window.UI, H = D.home, el = UI.el, clear = UI.clear, icon = UI.icon;
  var NAMES = { claude: 'AI limits', events: 'Up next', weather: 'Weather', media: 'Now playing', stats: 'PC stats', net: 'Internet', printer: '3D printer', game: 'Steam game', github: 'GitHub' };
  var ICONS = { claude: 'smart_toy', events: 'event', weather: 'wb_sunny', media: 'music_note', stats: 'speed', net: 'wifi', printer: 'view_in_ar', game: 'sports_esports', github: 'commit' };
  var MINW = { events: 2, media: 2, printer: 2, game: 2, github: 2 };                       // narrowest a card can be, in cells
  var DEF = { claude: [3, 1], events: [3, 1], weather: [2, 1], media: [2, 1], stats: [5, 1], net: [2, 1], printer: [3, 1], game: [3, 1], github: [5, 1] };
  var on = false, dirty = false, L = null, st = null, bar = null, tray = null, root = null, toastT = null, confirmT = null, ui = {};

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function addCls(n, c) { if ((' ' + n.className + ' ').indexOf(' ' + c + ' ') < 0) { n.className += ' ' + c; } }
  function rmCls(n, c) { n.className = (' ' + n.className + ' ').split(' ' + c + ' ').join(' ').replace(/^\s+|\s+$/g, ''); }
  function portrait() { return !!(window.matchMedia && window.matchMedia('(orientation: portrait)').matches); }
  function cellStyle(it) { return 'grid-column:' + (it.x + 1) + ' / span ' + it.w + ';grid-row:' + (it.y + 1) + ' / span ' + it.h; }
  function applyPos(card, it) { card.style.setProperty('grid-column', (it.x + 1) + ' / span ' + it.w); card.style.setProperty('grid-row', (it.y + 1) + ' / span ' + it.h); }
  function entryOf(it) { var cs = H.cards(), i; for (i = 0; i < cs.length; i++) { if (cs[i].it === it) { return cs[i]; } } return null; }

  // ---------------------------------------------------------------- the grid as numbers
  function hits(x, y, w, h, skip) {
    return L.items.filter(function (o) { return o !== skip && x < o.x + o.w && o.x < x + w && y < o.y + o.h && o.y < y + h; });
  }
  function spot(w, h) {
    var x, y;
    for (y = 0; y + h <= L.rows; y++) { for (x = 0; x + w <= L.cols; x++) { if (!hits(x, y, w, h, null).length) { return { x: x, y: y }; } } }
    return null;
  }
  function put(n) {   // first free place, shrinking to the smallest size when the wanted one has no room
    var sp = spot(n.w, n.h);
    if (!sp) { n.w = Math.min(L.cols, MINW[n.widget] || 1); n.h = 1; sp = spot(n.w, n.h); }
    if (!sp) { return false; }
    n.x = sp.x; n.y = sp.y; return true;
  }
  function geom() {
    var g = H.grid(), r = g.getBoundingClientRect(), cs = window.getComputedStyle(g);
    var gx = parseFloat(cs.columnGap || cs.gridColumnGap) || 0, gy = parseFloat(cs.rowGap || cs.gridRowGap) || gx;
    return { gx: gx, gy: gy, sx: (r.width - gx * (L.cols - 1)) / L.cols + gx, sy: (r.height - gy * (L.rows - 1)) / L.rows + gy };
  }

  // ---------------------------------------------------------------- feedback
  function toast(text) {
    var t = el('div', 'htoast', text); root.appendChild(t); clearTimeout(toastT);
    toastT = setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 2600);
  }
  function glide(card, it, x, y, before) {   // move a card to a cell and let it slide there from where it was
    before = before || card.getBoundingClientRect(); it.x = x; it.y = y;
    card.style.transition = 'none'; card.style.transform = ''; applyPos(card, it);
    var a = card.getBoundingClientRect();
    card.style.transform = 'translate3d(' + (before.left - a.left) + 'px,' + (before.top - a.top) + 'px,0)';
    void card.offsetWidth; card.style.transition = ''; card.style.transform = '';
  }

  // ---------------------------------------------------------------- dragging and resizing (landscape)
  function makeDrop() { var d = el('div', 'drop'); H.grid().appendChild(d); return d; }
  function showDrop() {
    st.drop.setAttribute('style', cellStyle({ x: st.nx, y: st.ny, w: st.nw, h: st.nh }));
    st.drop.className = 'drop' + (st.ok ? '' : ' bad');
  }
  function down(e, entry) {
    if (st || portrait() || (e.button && e.button !== 0)) { return; }
    var t = e.target, mode = t.className === 'eh' ? 'resize' : (t === entry.card ? 'move' : null);
    if (!mode) { return; }
    closeTray();
    var r = entry.card.getBoundingClientRect(), it = entry.it;
    st = { mode: mode, e: entry, g: geom(), x0: e.clientX, y0: e.clientY, id: e.pointerId, w0: r.width, h0: r.height, nx: it.x, ny: it.y, nw: it.w, nh: it.h, ok: true, swap: null, drop: makeDrop() };
    try { t.setPointerCapture(e.pointerId); } catch (err) { /* old browsers: the document listeners still get the moves */ }
    if (mode === 'move') { addCls(entry.card, 'drag'); }
    showDrop(); e.preventDefault();
  }
  function move(e) {
    if (!st || e.pointerId !== st.id) { return; }
    var dx = e.clientX - st.x0, dy = e.clientY - st.y0, it = st.e.it, g = st.g, hs;
    if (st.mode === 'move') {
      st.e.card.style.transform = 'translate3d(' + dx + 'px,' + dy + 'px,0) scale(1.02)';
      st.nx = clamp(Math.round(it.x + dx / g.sx), 0, L.cols - it.w); st.ny = clamp(Math.round(it.y + dy / g.sy), 0, L.rows - it.h);
    } else {
      st.nw = clamp(Math.round((st.w0 + dx + g.gx) / g.sx), Math.min(L.cols - it.x, MINW[it.widget] || 1), L.cols - it.x);
      st.nh = clamp(Math.round((st.h0 + dy + g.gy) / g.sy), 1, L.rows - it.y);
      st.e.sz.textContent = st.nw + '×' + st.nh;
    }
    hs = hits(st.nx, st.ny, st.nw, st.nh, it); st.swap = null; st.ok = hs.length === 0;
    if (!st.ok && st.mode === 'move' && hs.length === 1 && hs[0].w === it.w && hs[0].h === it.h) {   // same size: swap places
      st.swap = hs[0]; st.nx = hs[0].x; st.ny = hs[0].y; st.ok = true;
    }
    showDrop();
  }
  function up(e) {
    if (!st || (e && e.pointerId !== st.id)) { return; }
    var s = st, it = s.e.it, card = s.e.card; st = null;
    if (s.drop.parentNode) { s.drop.parentNode.removeChild(s.drop); }
    if (s.mode === 'move') {
      var before = card.getBoundingClientRect(); rmCls(card, 'drag');
      if (s.ok && (s.nx !== it.x || s.ny !== it.y)) {
        if (s.swap) { var oe = entryOf(s.swap); if (oe) { glide(oe.card, s.swap, it.x, it.y, null); } else { s.swap.x = it.x; s.swap.y = it.y; } }
        dirty = true; glide(card, it, s.nx, s.ny, before);
      } else { glide(card, it, it.x, it.y, before); }
    } else if (s.ok && (s.nw !== it.w || s.nh !== it.h)) {
      it.w = s.nw; it.h = s.nh; dirty = true; H.fill(card, it); bind(s.e); addCls(card, 'pop');
    } else { s.e.sz.textContent = it.w + '×' + it.h; }
  }
  document.addEventListener('pointermove', move, false);
  document.addEventListener('pointerup', up, false);
  document.addEventListener('pointercancel', up, false);

  // ---------------------------------------------------------------- cards in edit mode
  function bind(entry) {
    var card = entry.card, it = entry.it, hud = el('div', 'ehud'), x = el('button', 'ex'), eh = el('div', 'eh'), eo = el('div', 'eo'), bu = el('button'), bd = el('button');
    card.className = card.className.replace(/\s*\brise\b/g, '');
    addCls(card, 'edit');
    entry.sz = el('div', 'es', it.w + '×' + it.h);
    x.appendChild(icon('close')); bu.appendChild(icon('arrow_upward')); bd.appendChild(icon('arrow_downward')); eo.appendChild(bu); eo.appendChild(bd);
    hud.appendChild(el('div', 'en', NAMES[it.widget] || it.widget)); hud.appendChild(entry.sz); hud.appendChild(eo); hud.appendChild(x); hud.appendChild(eh); card.appendChild(hud);
    x.onclick = function () { remove(entry); }; bu.onclick = function () { shift(entry, -1); }; bd.onclick = function () { shift(entry, 1); };
    card.onpointerdown = function (e) { down(e, entry); };
  }
  function decorate() {
    var grid = H.grid(), i, j;
    for (j = L.rows - 1; j >= 0; j--) { for (i = L.cols - 1; i >= 0; i--) { var c = el('div', 'gcell'); c.setAttribute('style', 'grid-column:' + (i + 1) + ' / span 1;grid-row:' + (j + 1) + ' / span 1'); grid.insertBefore(c, grid.firstChild); } }
    H.cards().forEach(bind);
  }
  function redraw() { H.rebuild(); decorate(); updateBar(); }
  function remove(entry) {
    var card = entry.card, cs = H.cards(); addCls(card, 'gone');
    L.items = L.items.filter(function (i) { return i !== entry.it; }); cs.splice(cs.indexOf(entry), 1); H.unfill(card); dirty = true;
    setTimeout(function () { if (card.parentNode) { card.parentNode.removeChild(card); } }, 280);
  }
  function shift(entry, dir) {   // portrait: trade places with the next card in reading order
    var order = L.items.slice().sort(function (a, b) { return a.y - b.y || a.x - b.x; }), i = order.indexOf(entry.it), o = order[i + dir];
    if (!o) { return; }
    if (entry.it.w < (MINW[o.widget] || 1) || o.w < (MINW[entry.it.widget] || 1)) { toast('Those two cards cannot trade places'); return; }
    var tmp = entry.it.widget; entry.it.widget = o.widget; o.widget = tmp; dirty = true; redraw();
  }
  function add(name) {
    var d = DEF[name] || [2, 1], n = { widget: name, x: 0, y: 0, w: Math.min(d[0], L.cols), h: Math.min(d[1], L.rows) };
    if (!put(n)) { toast('No room: remove or shrink a card first'); return; }
    L.items.push(n); dirty = true; closeTray();
    var card = el('div', 'card'), entry = { it: n, card: card }; H.fill(card, n); H.grid().appendChild(card); H.cards().push(entry); bind(entry); addCls(card, 'pop');
  }
  function setGrid(c, r) {
    c = clamp(c, 3, 6); r = clamp(r, 2, 4); if (c === L.cols && r === L.rows) { return; }
    var items = L.items.slice().sort(function (a, b) { return a.y - b.y || a.x - b.x; }), lost = 0;
    L.cols = c; L.rows = r; L.items = [];
    items.forEach(function (it) {
      var w = Math.min(it.w, L.cols), h = Math.min(it.h, L.rows), n = { widget: it.widget, x: Math.min(it.x, L.cols - w), y: Math.min(it.y, L.rows - h), w: w, h: h };
      if (hits(n.x, n.y, n.w, n.h, null).length && !put(n)) { lost++; return; }
      L.items.push(n);
    });
    dirty = true; if (lost) { toast(lost + (lost > 1 ? ' cards did' : ' card did') + ' not fit and were removed'); }
    redraw();
  }

  // ---------------------------------------------------------------- toolbar and tray
  function stepper(label, get, set) {
    var box = el('div', 'stepper'), m = el('button', null, '−'), p = el('button', null, '+'), t = el('span'), b = el('b');
    t.appendChild(document.createTextNode(label + ' ')); t.appendChild(b); box.appendChild(m); box.appendChild(t); box.appendChild(p);
    m.onclick = function () { set(get() - 1); }; p.onclick = function () { set(get() + 1); };
    return { root: box, show: function () { b.textContent = String(get()); } };
  }
  function updateBar() { ui.cols.show(); ui.rows.show(); ui.clock.textContent = L.clock ? 'Clock: on' : 'Clock: off'; }
  function buildBar() {
    bar = el('div'); bar.id = 'hedit';
    var done = el('button', 'btn', 'Done'), plus = el('button', 'btn ghost', '+ Add'), sp = el('div', 'grow'), reset = el('button', 'btn ghost', 'PC layout');
    ui.cols = stepper('Cols', function () { return L.cols; }, function (v) { setGrid(v, L.rows); });
    ui.rows = stepper('Rows', function () { return L.rows; }, function (v) { setGrid(L.cols, v); });
    ui.clock = el('button', 'btn ghost', 'Clock: on');
    done.onclick = finish; plus.onclick = openTray;
    ui.clock.onclick = function () { L.clock = !L.clock; dirty = true; updateBar(); };
    reset.onclick = function () {   // two taps, because it throws the phone's layout away
      if (reset.textContent === 'PC layout') { reset.textContent = 'Sure?'; clearTimeout(confirmT); confirmT = setTimeout(function () { reset.textContent = 'PC layout'; }, 3000); return; }
      reset.textContent = 'PC layout'; clearTimeout(confirmT); resetLayout();
    };
    [done, plus, ui.cols.root, ui.rows.root, ui.clock, sp, reset].forEach(function (n) { bar.appendChild(n); });
    root.insertBefore(bar, H.grid());
    tray = el('div'); tray.id = 'htray'; root.appendChild(tray);
  }
  function openTray() {
    var have = {}, any = false, name, opts = el('div', 'opts'), head = el('div', 'row'), close = el('button', 'cbtn'), cap = el('div', 'cap grow', 'Add a card');
    L.items.forEach(function (i) { have[i.widget] = 1; });
    clear(tray); close.appendChild(icon('close')); close.style.width = close.style.height = '2rem'; close.onclick = closeTray; head.appendChild(cap); head.appendChild(close); tray.appendChild(head);
    var bs = H.builders();
    Object.keys(NAMES).forEach(function (k) {
      if (!bs[k] || have[k]) { return; }
      var b = el('button', 'opt'); b.appendChild(icon(ICONS[k] || 'widgets')); b.appendChild(document.createTextNode(NAMES[k])); b.onclick = function () { add(k); }; opts.appendChild(b); any = true;
    });
    if (!any) { opts.appendChild(el('div', 'sub', 'Every card is already on Home.')); }
    tray.appendChild(opts); void tray.offsetWidth; tray.className = 'on';
  }
  function closeTray() { if (tray) { tray.className = ''; } }

  // ---------------------------------------------------------------- start and stop
  function start() {
    if (on) { return; }
    if (!bar) { return; }
    if (D.page() !== 'home') { D.show('home'); }
    var base = H.layout();
    L = { cols: base.cols, rows: base.rows, clock: base.clock, items: base.items }; dirty = false; on = true;
    H.editing(true, L); addCls(root, 'editing'); redraw();
  }
  function leave() { on = false; st = null; closeTray(); rmCls(root, 'editing'); H.editing(false); }
  function finish() {
    if (!on) { return; }
    var save = dirty, l = L; leave();
    if (save) { H.save(l); }
    H.rebuild();
  }
  function resetLayout() { leave(); H.forget(); toast('Using the PC\'s layout'); }

  var origStart = D.start;
  D.start = function (opts) {
    origStart(opts);
    root = H.root(); buildBar();
    var b = el('button', 'edit-btn'); b.setAttribute('aria-label', 'Edit the home screen'); b.appendChild(icon('edit')); b.onclick = start; document.getElementById('top').appendChild(b);
    if (D.pages.home) { D.pages.home.hide = function () { finish(); }; }
  };
  D.homeEdit = { start: start, finish: finish, reset: resetLayout };
})();
