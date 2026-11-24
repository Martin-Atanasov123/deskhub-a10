/* DeskHub display shell: connection, power, navigation, page transitions, Home and Settings.
   ES5 on purpose (old Android WebViews): no arrow functions, let/const, template strings. */
(function () {
  'use strict';
  var UI = window.UI, el = UI.el, clear = UI.clear, pad = UI.pad, icon = UI.icon;
  var T0 = Date.now();
  function $(id) { return document.getElementById(id); }

  var mem = {};
  function load(k, d) {
    try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return mem.hasOwnProperty(k) ? mem[k] : d; }
  }
  function save(k, v) { mem[k] = v; try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  function drop(k) { delete mem[k]; try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }

  // Pairing: the QR code carries the token in the URL fragment; keep it, then hide it.
  (function () {
    var m = /[#&]t=([^&]+)/.exec(location.hash);
    if (m) {
      save('dh_token', decodeURIComponent(m[1]));
      try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { location.hash = ''; }
    }
  })();
  function token() { return load('dh_token', ''); }

  var reduced = false;
  try { reduced = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { /* old browser */ }
  var cfg = {
    // normal | low (Eco, the default: this runs on a battery) | ultra (Battery saver): how often data arrives
    mode: (function (m) { return m === 'normal' || m === 'ultra' ? m : 'low'; })(load('dh_mode', 'low')),
    // full | min | off: how much the screen animates. Independent of the power mode (it only costs while it moves)
    motion: (function (m) { return m === 'min' || m === 'off' || m === 'full' ? m : (reduced ? 'min' : 'full'); })(load('dh_motion', '')),
    dim: parseInt(load('dh_dim', '0'), 10) || 0,
    sleepMin: parseInt(load('dh_sleep', '0'), 10) || 0,
    wake: load('dh_wake', '0') === '1'
  };
  UI.setMotion(cfg.motion);

  var S = {
    layout: null, home: null, tiles: [], lit: [], stats: null, media: null, mediaAt: 0, events: null,
    ai: null, net: null, msg: {}, pcAsleep: false, hist: [], lastMsg: 0, status: 'connecting', version: '', battery: null,
    alertId: '', rxBytes: 0, rxCount: 0, smooth: null, gotData: false
  };
  var curPage = load('dh_page', 'home');
  var lastTouch = Date.now(), awakeUntil = 0, sleeping = null;

  // ---------------------------------------------------------------- reporting problems to the PC
  var lastReport = '', lastReportAt = 0;
  function report(level, msg) {
    msg = String(msg).slice(0, 280);
    var now = Date.now();
    if (msg === lastReport && now - lastReportAt < 5000) { return; }
    lastReport = msg; lastReportAt = now;
    if (ws && ws.readyState === 1) { send({ type: 'log', level: level, msg: msg }); return; }
    try {
      var x = new XMLHttpRequest();
      x.open('POST', '/api/log');
      x.setRequestHeader('Content-Type', 'application/json');
      if (token()) { x.setRequestHeader('X-Token', token()); }
      x.send(JSON.stringify({ level: level, msg: msg }));
    } catch (e) { /* nowhere to report to */ }
  }
  window.onerror = function (msg, src, line) { report('error', msg + ' (line ' + line + ')'); };

  // ---------------------------------------------------------------- connection
  var ws = null, retries = 0, reconnects = 0, retryTimer = null, denied = false;

  function wsUrl() { return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws'; }
  function effMode() { return sleeping ? 'idle' : cfg.mode; }
  // How long without any message (the PC sends a heartbeat every 4/10/20/60 s) means the link is dead.
  function staleMs() { var m = effMode(); return m === 'normal' ? 12000 : m === 'low' ? 30000 : m === 'ultra' ? 60000 : 150000; }
  function send(obj) { if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; } return false; }

  var bootTimer = null;
  function bootHide() { $('boot').className = 'gone'; clearTimeout(bootTimer); bootTimer = null; }
  function setStatus(s, detail) {
    S.status = s; S.statusDetail = detail || '';
    $('link').className = s;
    var toast = $('toast');
    var text = s === 'connecting' ? 'Connecting' : s === 'offline' ? 'PC not reachable' + (detail ? ', trying again in ' + detail : '') : '';
    if (text) { $('toast-text').textContent = text; }
    toast.className = text ? 'on' : '';
    $('pair').className = 'overlay' + (s === 'pair' || s === 'denied' ? ' on' : '');
    if (s === 'denied') { $('pair-text').textContent = 'The PC did not accept that code. Scan the QR code on the PC again, or retype the code.'; }
    if (s === 'pair' || s === 'denied') { bootHide(); }
    else if (s === 'offline' && !bootTimer && $('boot').className !== 'gone') { bootTimer = setTimeout(bootHide, 4500); }
    else if (s === 'paused') { bootHide(); }
    var bt = $('boot-text'); if (bt) { bt.textContent = s === 'offline' ? 'PC not reachable, trying again' : 'Connecting to your PC'; }
  }

  function connect() {
    clearTimeout(retryTimer); retryTimer = null;
    if (S.demo) { return; }   // ?demo=1 shows sample data and never opens a connection
    if (!token()) { setStatus('pair'); return; }
    if (denied) { setStatus('denied'); return; }
    if (document.hidden) { setStatus('paused'); return; }
    if (ws && (ws.readyState === 0 || ws.readyState === 1)) { return; }
    setStatus('connecting');
    var s;
    try { s = new WebSocket(wsUrl()); } catch (e) { report('error', 'WebSocket constructor: ' + e); schedule(); return; }
    ws = s;
    S.lastMsg = Date.now();   // the "gone quiet" clock starts now, so a link that opens but never answers is noticed too
    // A connection attempt that never answers (a half-dead Wi-Fi link) must not leave the page waiting forever.
    var guard = setTimeout(function () {
      if (ws === s && !S.helloOk) {
        report('warn', 'no answer from the PC within 10 s; trying again');
        closeSocket(); schedule();
      }
    }, 10000);
    S.helloOk = false;
    s.onopen = function () { s.send(JSON.stringify({ type: 'hello', token: token(), mode: effMode() })); };
    s.onmessage = function (ev) {
      S.lastMsg = Date.now(); S.rxBytes += ev.data.length; S.rxCount++;
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      onMessage(m);
    };
    s.onclose = function () {
      clearTimeout(guard);
      if (ws !== s) { return; }   // closed on purpose (paused, replaced)
      ws = null;
      if (!denied) { setStatus('offline'); schedule(); } else { setStatus('denied'); }
    };
    s.onerror = function () { /* onclose follows */ };
  }

  function schedule() {
    if (retryTimer) { return; }
    var wait = Math.min(30000, 1000 * Math.pow(2, Math.min(retries, 5)));
    retries++; reconnects++;
    setStatus('offline', Math.round(wait / 1000) + ' s');
    retryTimer = setTimeout(connect, wait);
  }

  function closeSocket() { var s = ws; ws = null; if (s) { try { s.close(); } catch (e) { /* gone */ } } }

  // After the browser resumes or the phone wakes: reconnect now, don't wait for a timer.
  function resume(why) {
    if (document.hidden || denied) { return; }
    var stale = ws && ws.readyState === 1 && Date.now() - S.lastMsg > staleMs();
    if (!ws || ws.readyState > 1 || stale || S.status !== 'online') {
      if (stale) { report('info', 'stale connection after ' + why + ', reconnecting'); }
      closeSocket(); retries = 0; clearTimeout(retryTimer); retryTimer = null; connect();
    }
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { closeSocket(); S.lastMsg = 0; setStatus('paused'); }   // let the radio rest
    else { applyWake(); tickClock(); resume('visible'); }
    syncTicks();
  });
  window.addEventListener('pageshow', function () { resume('pageshow'); });
  window.addEventListener('online', function () { resume('online'); });
  window.addEventListener('focus', function () { resume('focus'); });
  // The browser can freeze a page (screen locked, tab in the background) without any event reaching us.
  document.addEventListener('freeze', function () { closeSocket(); S.lastMsg = 0; });
  document.addEventListener('resume', function () { resume('resume'); });
  try { if (navigator.connection) { navigator.connection.addEventListener('change', function () { resume('network change'); }); } } catch (e) { /* no such API */ }
  // Safety net: a socket that looks open but has gone quiet, or none at all.
  var lastTick = Date.now();
  setInterval(function () {
    var now = Date.now(), gap = now - lastTick;   // a timer that fires after 20 s instead of 5 s: the page was suspended
    lastTick = now;
    if (document.hidden || denied || !token()) { return; }
    if (gap > 20000) { report('info', 'timers were paused for ' + Math.round(gap / 1000) + ' s (suspended?); checking the connection'); resume('suspend'); return; }
    if (ws && ws.readyState === 1 && S.lastMsg && Date.now() - S.lastMsg > staleMs()) {
      report('warn', 'no data for ' + Math.round((Date.now() - S.lastMsg) / 1000) + ' s, reconnecting');
      closeSocket(); retries = 0; connect();
    } else if (!ws && !retryTimer) { connect(); }
  }, 5000);

  // ---------------------------------------------------------------- power: eco mode, dimming, sleep
  function sendPower() { send({ type: 'power', mode: effMode() }); }
  function setMode(m) {
    cfg.mode = m === 'normal' || m === 'ultra' ? m : 'low'; save('dh_mode', cfg.mode);
    armClock(); sendPower(); syncTicks();
  }
  function setMotion(m) { cfg.motion = m; save('dh_motion', m); UI.setMotion(m); }
  function applyDim() { $('dim').style.opacity = String(Math.min(70, cfg.dim) / 100); }

  function inNight(a, b) {
    var d = new Date(), n = d.getHours() * 60 + d.getMinutes();
    return a < b ? (n >= a && n < b) : (n >= a || n < b);
  }
  function wantSleep() {
    var now = Date.now(), L = S.layout || {};
    if (now < awakeUntil) { return null; }
    if (S.pcAsleep && L.pc_sleep && L.pc_sleep !== 'none') { return L.pc_sleep; }
    if (typeof L.night_start === 'number' && L.night_start >= 0 && inNight(L.night_start, L.night_end)) { return L.night_style || 'off'; }
    if (cfg.sleepMin > 0 && now - lastTouch > cfg.sleepMin * 60000) { return 'clock'; }
    return null;
  }
  function applySleep() {
    var want = wantSleep();
    if (want !== sleeping) {
      sleeping = want;
      $('sleep').className = 'overlay' + (want ? ' on ' + want : '');
      sendPower(); armClock(); tickClock(); syncTicks();
    }
  }
  function touched() { lastTouch = Date.now(); awakeUntil = lastTouch + 60000; if (sleeping) { applySleep(); } }
  document.addEventListener('touchstart', touched, false);
  document.addEventListener('mousedown', touched, false);
  setInterval(applySleep, 10000);

  var wakeSentinel = null;
  function applyWake() {   // only exists in a "secure context"; see docs/LIMITATIONS.md
    if (!cfg.wake || !navigator.wakeLock || document.hidden || wakeSentinel) { return; }
    navigator.wakeLock.request('screen').then(function (s) {
      wakeSentinel = s; s.addEventListener('release', function () { wakeSentinel = null; });
    }, function (e) { report('warn', 'wake lock refused: ' + e); });
  }
  try {
    if (navigator.getBattery) {
      navigator.getBattery().then(function (b) {
        function upd() { S.battery = Math.round(b.level * 100) + '% ' + (b.charging ? 'charging' : 'on battery'); }
        upd(); b.onlevelchange = upd; b.onchargingchange = upd;
      }, function () { /* not allowed here */ });
    }
  } catch (e) { /* no battery API */ }

  // ---------------------------------------------------------------- clock
  var clockTimer = null;
  function tickClock() {
    var d = new Date(), t = UI.time(d), c = $('clock'), tn = $('clock-t');
    if (tn) { tn.textContent = t.t; $('clock-ap').textContent = t.ap; $('date').textContent = UI.dateLong(d); }
    $('sleep-clock').textContent = t.t;
  }
  function armClock() {
    clearInterval(clockTimer);
    clockTimer = setInterval(tickClock, effMode() === 'normal' ? 5000 : effMode() === 'low' ? 20000 : 30000);
  }

  // ---------------------------------------------------------------- images with the pairing code (cover art, game covers)
  var blobs = {}, blobOrder = [], failed = {};
  function image(img, url) {
    img.className = img.className.replace(/\s*\bon\b/, '');
    if (!url) { img.removeAttribute('src'); return; }
    function show(u) { img.src = u; img.className += ' on'; }
    if (blobs[url]) { show(blobs[url]); return; }
    if (failed[url] && Date.now() - failed[url] < 600000) { return; }   // no image there: do not ask again for 10 minutes
    var x = new XMLHttpRequest(), tok = token();
    x.open('GET', url); x.responseType = 'blob';
    if (tok) { x.setRequestHeader('X-Token', tok); }
    x.onerror = function () { failed[url] = Date.now(); };
    x.onload = function () {
      if (x.status !== 200) { failed[url] = Date.now(); return; }
      var U = window.URL || window.webkitURL, u = U.createObjectURL(x.response);
      blobs[url] = u; blobOrder.push(url);
      if (blobOrder.length > 24) { var old = blobOrder.shift(); try { U.revokeObjectURL(blobs[old]); } catch (e) { /* ignore */ } delete blobs[old]; }
      show(u);
    };
    x.send();
  }

  // ---------------------------------------------------------------- Home
  var builders = {}, widgets = [];
  var TITLES = { clock: 'Clock' };
  var DEFAULT_GRID = [
    { widget: 'claude', x: 0, y: 0, w: 3, h: 1 }, { widget: 'weather', x: 3, y: 0, w: 2, h: 1 }, { widget: 'events', x: 0, y: 1, w: 3, h: 1 },
    { widget: 'media', x: 3, y: 1, w: 2, h: 1 }, { widget: 'stats', x: 0, y: 2, w: 5, h: 1 }
  ];
  function buildHomePage(root) {
    var top = el('div'); top.id = 'top';
    var clock = el('div'); clock.id = 'clock';
    var t = el('span'); t.id = 'clock-t'; var ap = el('span', 'ap'); ap.id = 'clock-ap'; clock.appendChild(t); clock.appendChild(ap);
    var date = el('div'); date.id = 'date';
    top.appendChild(clock); top.appendChild(date);
    var grid = el('div'); grid.id = 'grid';
    root.appendChild(top); root.appendChild(grid);
  }
  // The grid comes from this phone's own layout when there is one (Home > the pencil), otherwise from the PC's config, otherwise the default.
  var homeCards = [], homeOverride = null, homeEditing = false;
  function clampN(v, lo, hi, dflt) { v = parseInt(v, 10); return isNaN(v) ? dflt : Math.max(lo, Math.min(hi, v)); }
  function homeLayout() {
    var l = null, items, i, out = [];
    try { l = JSON.parse(load('dh_home', '')); } catch (e) { l = null; }
    if (l && l.items && typeof l.items.length === 'number') {
      for (i = 0; i < l.items.length; i++) { var it = l.items[i]; if (it && builders[it.widget]) { out.push({ widget: it.widget, x: clampN(it.x, 0, 5, 0), y: clampN(it.y, 0, 3, 0), w: clampN(it.w, 1, 6, 1), h: clampN(it.h, 1, 4, 1) }); } }
      return { cols: clampN(l.cols, 3, 6, 5), rows: clampN(l.rows, 2, 4, 3), clock: l.clock !== false, items: out, custom: true };
    }
    items = (S.home && S.home.grid && S.home.grid.length) ? S.home.grid : DEFAULT_GRID;
    for (i = 0; i < items.length; i++) { out.push({ widget: items[i].widget, x: items[i].x, y: items[i].y, w: items[i].w, h: items[i].h }); }
    return { cols: 5, rows: 3, clock: true, items: out, custom: false };
  }
  // Put one widget in its card: size classes, grid cell, content. Replaces whatever the card showed before.
  function fillCard(card, it) {
    widgets = widgets.filter(function (w) { if (w.card === card) { return false; } return true; });
    clear(card); card.className = 'card' + (it.w >= 4 || it.h >= 2 ? ' wide' : '') + (it.h >= 2 ? ' tall' : '');
    card.setAttribute('style', 'grid-column:' + (it.x + 1) + ' / span ' + it.w + ';grid-row:' + (it.y + 1) + ' / span ' + it.h);
    if (builders[it.widget]) { var w = builders[it.widget](card, it); w.card = card; widgets.push(w); w.update(); }
    else { card.appendChild(el('div', 'cap', TITLES[it.widget] || it.widget)); card.appendChild(el('div', 'sub', 'Not in this version yet')); }
  }
  function buildHome() {
    var grid = $('grid'), L = homeOverride || homeLayout(), cards = [];
    clear(grid); widgets = []; homeCards = [];
    grid.style.setProperty('--cols', String(L.cols)); grid.style.setProperty('--rows', String(L.rows));
    $('top').style.display = L.clock && !homeEditing ? '' : 'none';
    // Reading order (top to bottom, left to right): it is the order the cards stack in on a portrait screen.
    L.items.slice().sort(function (a, b) { return a.y - b.y || a.x - b.x; }).forEach(function (it) {
      if (it.widget === 'clock') { return; }   // the clock lives in the top bar
      var card = el('div', 'card'); fillCard(card, it); grid.appendChild(card); cards.push(card); homeCards.push({ it: it, card: card });
    });
    UI.rise(cards);
  }
  function homeSave(L) {
    save('dh_home', JSON.stringify({ cols: L.cols, rows: L.rows, clock: L.clock, items: L.items.map(function (i) { return { widget: i.widget, x: i.x, y: i.y, w: i.w, h: i.h }; }) }));
  }
  // Only the page on screen is drawn; the others catch up when opened (less work for the phone).
  var homeDirty = false, dirtyPages = {};
  function refresh(kind) {
    if (curPage !== 'home') { homeDirty = true; return; }
    widgets.forEach(function (w) { if (w.kind === kind) { w.update(); } });
  }

  // ---------------------------------------------------------------- Settings
  var info = {};
  function kv(parent, k) { var r = el('div', 'kv'); r.appendChild(el('span', null, k)); info[k] = el('span', null, ''); r.appendChild(info[k]); parent.appendChild(r); }
  function section(parent, title) { var c = el('div', 'card set-card'); c.appendChild(el('div', 'cap', title)); parent.appendChild(c); return c; }
  function buildSettings() {
    var root = $('page-set'); clear(root); info = {};
    var box = el('div', 'set-page scroll'), c;
    box.appendChild(el('h1', null, 'Settings'));
    c = section(box, 'Power');
    c.appendChild(UI.segmented([['normal', 'Normal'], ['low', 'Eco'], ['ultra', 'Battery saver']], cfg.mode, setMode).root);
    c.lastChild.className += ' seg-wide';
    c.appendChild(el('p', null, 'How often numbers arrive: every second, every 5 s, every 15 s. The screen itself uses far more power than any of these: lower the phone\'s brightness and let it time out.'));
    c = section(box, 'Home screen');
    var hrow = el('div', 'link-row'), he = el('button', 'btn', 'Edit home screen'), hr = el('button', 'btn ghost', 'Use the PC\'s layout');
    he.onclick = function () { if (window.DH.homeEdit) { window.DH.homeEdit.start(); } };
    hr.onclick = function () { if (window.DH.homeEdit) { window.DH.homeEdit.reset(); } hr.style.display = 'none'; };
    hr.style.display = window.DH.home.custom() ? '' : 'none'; hrow.appendChild(he); hrow.appendChild(hr); c.appendChild(hrow);
    c.appendChild(el('p', null, 'Choose which cards Home shows, where they sit and how big they are. It is saved on this phone only.'));
    c = section(box, 'Animations');
    c.appendChild(UI.segmented([['full', 'Full'], ['min', 'Minimal'], ['off', 'Off']], cfg.motion, setMotion).root);
    c.lastChild.className += ' seg-wide';
    var out = el('div', 'smooth-out');
    var test = el('button', 'btn ghost', 'Test smoothness'); test.style.marginTop = '.6rem';
    test.onclick = function () {
      test.disabled = true; out.textContent = 'Testing...';
      var ids = pageOrder().filter(function (i) { return i !== 'set'; });
      UI.smoothness(function (id) { showPage(id); }, ids, function (r) {
        S.smooth = Math.round(1000 / Math.max(1, r.avg)) + ' fps average, slowest frame ' + Math.round(r.worst) + ' ms, ' + r.slow + ' of ' + r.frames + ' frames over 25 ms';
        report('info', 'smoothness test: ' + S.smooth);
        showPage('set');
      });
    };
    c.appendChild(test); c.appendChild(out);
    if (S.smooth) { out.textContent = S.smooth; }
    c.appendChild(el('p', null, 'Animations only cost power while something moves. Off or Minimal if you want every last bit of battery.'));
    c = section(box, 'Screen');
    var rng = el('input'); rng.type = 'range'; rng.min = 0; rng.max = 70; rng.step = 5; rng.value = cfg.dim;
    rng.oninput = function () { cfg.dim = parseInt(rng.value, 10); save('dh_dim', String(cfg.dim)); applyDim(); };
    c.appendChild(rng);
    c.appendChild(el('p', null, 'Dims the picture for the evening. It does not lower the backlight; use the phone\'s own brightness slider for battery.'));
    var sl = UI.segmented([[0, 'No dark clock'], [2, '2 min'], [5, '5 min'], [10, '10 min']], cfg.sleepMin, function (v) { cfg.sleepMin = v; save('dh_sleep', String(v)); lastTouch = Date.now(); });
    sl.root.className += ' seg-wide'; sl.root.style.marginTop = '.7rem'; c.appendChild(sl.root);
    var row = el('div', 'link-row');
    var fs = el('button', 'btn ghost', 'Fullscreen');
    fs.onclick = function () { var e = document.documentElement; (e.requestFullscreen || e.webkitRequestFullscreen || function () {}).call(e); };
    row.appendChild(fs);
    if (navigator.wakeLock) {
      var wl = el('button', 'btn ghost', cfg.wake ? 'Keep screen on: yes' : 'Keep screen on: no');
      wl.onclick = function () { cfg.wake = !cfg.wake; save('dh_wake', cfg.wake ? '1' : '0'); wl.textContent = cfg.wake ? 'Keep screen on: yes' : 'Keep screen on: no';
        if (cfg.wake) { applyWake(); } else if (wakeSentinel) { wakeSentinel.release(); } };
      row.appendChild(wl);
    }
    c.appendChild(row);
    if (!navigator.wakeLock) { c.appendChild(el('p', null, 'This browser cannot keep the screen on over plain http. See docs/LIMITATIONS.md for the options.')); }
    c = section(box, 'Connection');
    ['Status', 'PC address', 'Server', 'Last data', 'Received', 'Reconnects', 'Power mode', 'Screen', 'Battery'].forEach(function (k) { kv(c, k); });
    row = el('div', 'link-row');
    var a1 = el('a', 'btn ghost', 'Compatibility test'); a1.href = 'compat'; var a2 = el('a', 'btn ghost', 'Diagnostics'); a2.href = 'diag';
    var forget = el('button', 'btn ghost', 'Forget this PC');
    forget.onclick = function () { drop('dh_token'); closeSocket(); denied = false; setStatus('pair'); };
    row.appendChild(a1); row.appendChild(a2); row.appendChild(forget); c.appendChild(row);
    root.appendChild(box); updateSettingsInfo();
  }
  function updateSettingsInfo() {
    if (!info.Status) { return; }
    info.Status.textContent = S.status; info['PC address'].textContent = location.host; info.Server.textContent = S.version || '-';
    info['Last data'].textContent = S.lastMsg ? Math.round((Date.now() - S.lastMsg) / 1000) + ' s ago' : '-';
    info.Received.textContent = (S.rxBytes / 1024).toFixed(1) + ' KB in ' + S.rxCount + ' messages';
    info.Reconnects.textContent = String(reconnects); info['Power mode'].textContent = effMode();
    info.Screen.textContent = window.innerWidth + ' x ' + window.innerHeight + ' @' + (window.devicePixelRatio || 1) + 'x';
    info.Battery.textContent = S.battery || 'not available in this browser';
  }
  // Timers that exist only while their page is open.
  var settingsTick = null;
  function syncTicks() {
    var need = curPage === 'set' && !document.hidden;
    if (need && !settingsTick) { settingsTick = setInterval(updateSettingsInfo, 2000); }
    else if (!need && settingsTick) { clearInterval(settingsTick); settingsTick = null; }
    var pg = PAGES[curPage];
    if (pg && pg.sync) { pg.sync(); }
    for (var id in PAGES) { if (id !== curPage && PAGES[id].sync) { PAGES[id].sync(); } }
  }

  // ---------------------------------------------------------------- navigation
  // Every page registers here ({icon, label, key, build, update, kinds, show, hide, sync, navIcon, navLabel, badge}).
  // "key" is the page's name in the PC's [pages] list; the navigation follows the order of that list.
  var PAGES = {
    home: { icon: 'home', label: 'Home', key: 'home' },
    set: { icon: 'tune', label: 'Settings', key: null }
  };
  var DEFAULT_ORDER = ['home', 'stats', 'ai', 'calendar', 'weather', 'media', 'printer', 'timer', 'games', 'github', 'keys'];
  function pageOrder() {
    var ids = [], pages = S.layout && S.layout.pages, id;
    if (pages) {
      pages.forEach(function (k) {
        for (id in PAGES) { if (PAGES[id].key === k && ids.indexOf(id) < 0) { ids.push(id); } }
      });
    } else {
      DEFAULT_ORDER.forEach(function (i) { if (PAGES[i]) { ids.push(i); } });
    }
    if (ids.indexOf('home') < 0) { ids.unshift('home'); }
    ids = ids.filter(function (i) { return i !== 'keys' || S.tiles.length; });
    ids.push('set');
    return ids;
  }
  var navSig = '', navBtns = {};
  function navMode() {   // portrait and short landscape screens: a bottom bar, like the original on its short screen
    var portrait = window.innerHeight > window.innerWidth;
    if (portrait || window.innerHeight < 440) { return 'bottom'; }
    var n = S.layout && S.layout.nav;
    return n === 'right' || n === 'bottom' ? n : 'left';
  }
  function buildNav() {
    var ids = pageOrder(), sig = ids.join(',') + '|' + navMode() + '|' + (S.ai ? S.ai.provider : ''), wrap = $('navbtns');
    document.body.setAttribute('data-nav', navMode());
    if (sig !== navSig) {
      navSig = sig; navBtns = {};
      var old = wrap.querySelectorAll('.nbtn'), i;
      for (i = old.length - 1; i >= 0; i--) { wrap.removeChild(old[i]); }
      ids.forEach(function (id) {
        var pg = PAGES[id], b = el('button', 'nbtn');
        b.setAttribute('aria-label', pg.label);
        b.appendChild(pg.navIcon ? pg.navIcon() : icon(pg.icon));
        b.appendChild(el('span', 'badge'));
        b.onclick = function () { showPage(id); };
        wrap.appendChild(b); navBtns[id] = b;
      });
    }
    updateNav();
  }
  function updateNav() {
    var id, b, pg;
    for (id in navBtns) {
      b = navBtns[id]; pg = PAGES[id];
      b.className = 'nbtn' + (id === curPage ? ' on' : '');
      var lab = pg.navLabel && pg.navLabel(), ln = b.querySelector('.navlabel');
      if (lab) { if (!ln) { ln = el('span', 'navlabel'); b.appendChild(ln); } ln.textContent = lab; } else if (ln) { b.removeChild(ln); }
      var bd = b.querySelector('.badge');
      if (bd) { bd.className = 'badge' + (pg.badge && pg.badge() ? ' on' : ''); }
    }
    placePill();
  }
  function placePill() {
    var b = navBtns[curPage], pill = $('pill');
    if (!b) { pill.style.opacity = '0'; return; }
    pill.style.opacity = '1';
    pill.style.width = b.offsetWidth + 'px'; pill.style.height = b.offsetHeight + 'px';
    pill.style.transform = 'translate3d(' + b.offsetLeft + 'px,' + b.offsetTop + 'px,0)';
  }
  window.addEventListener('resize', function () { buildNav(); });

  var shown = false;
  function showPage(p) {
    if (!PAGES[p]) { p = 'home'; }
    var prev = curPage, ids = pageOrder();
    curPage = p; save('dh_page', p);
    var dir = ids.indexOf(p) >= ids.indexOf(prev) ? 1 : -1;
    var next = $('page-' + p), old = prev !== p ? $('page-' + prev) : null, shift = (cfg.motion === 'full' ? 1.5 : 0.01) * dir;
    if (prev !== p && PAGES[prev] && PAGES[prev].hide) { PAGES[prev].hide(); }
    if (next && next.className.indexOf(' on') < 0) {   // start from the side it comes from, without animating there
      next.style.transition = 'none'; next.style.setProperty('--dx', shift + 'rem'); void next.offsetWidth; next.style.transition = '';
    }
    if (old) { old.style.setProperty('--dx', (-shift * .8) + 'rem'); }
    var secs = document.querySelectorAll('.page'), i;
    for (i = 0; i < secs.length; i++) {
      var on = secs[i].id === 'page-' + p;
      if (on) { if (secs[i].className.indexOf(' on') < 0) { secs[i].className += ' on'; } }
      else { secs[i].className = secs[i].className.replace(/\s*\bon\b/g, ''); }
    }
    buildNav();
    if (p === 'set') { buildSettings(); }
    if (p === 'home' && homeDirty) { homeDirty = false; widgets.forEach(function (w) { w.update(); }); }
    if (dirtyPages[p]) { dirtyPages[p] = false; PAGES[p].update(PAGES[p].kinds[0]); }
    if (PAGES[p].show) { PAGES[p].show(); }
    syncTicks();
    shown = true;
  }
  // Tell registered pages that a message of this kind arrived (the open one redraws now, the rest when opened).
  function notify(kind) {
    for (var id in PAGES) {
      var pg = PAGES[id];
      if (pg.update && pg.kinds && pg.kinds.indexOf(kind) >= 0) {
        if (id === curPage) { pg.update(kind); } else { dirtyPages[id] = true; }
      }
    }
  }

  // ---------------------------------------------------------------- alerts (an agent waiting for you)
  function showAlert(m) {
    var card = $('alertcard');
    if (m.clear || m.active === false) { card.className = ''; S.alertId = ''; updateNav(); return; }
    S.alertId = m.id || '';
    $('alert-title').textContent = m.title || 'Waiting for you';
    $('alert-project').textContent = m.project || m.agent || '';
    var lg = $('alert-logo'); clear(lg); lg.className = 'logo-tile' + (m.agent === 'codex' ? ' codex' : ''); lg.appendChild(UI.logo(m.agent === 'codex' ? 'codex' : 'claude', 26));
    card.className = 'on'; updateNav();
  }
  $('alert-focus').onclick = function () { send({ type: 'alert_action', id: S.alertId, action: 'focus' }); };
  $('alert-dismiss').onclick = function () { send({ type: 'alert_action', id: S.alertId, action: 'dismiss' }); $('alertcard').className = ''; S.alertId = ''; updateNav(); };

  // ---------------------------------------------------------------- fullscreen prompt
  // Asked once per browser session while the page is not fullscreen / installed; "Don't ask again" is remembered.
  function inFullscreen() {
    var standalone = false;
    try { standalone = !!(window.matchMedia && window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches); } catch (e) { /* old browser */ }
    return !!(document.fullscreenElement || document.webkitFullscreenElement || standalone);
  }
  function goFullscreen() { var e = document.documentElement; (e.requestFullscreen || e.webkitRequestFullscreen || function () {}).call(e); }
  function fsAskMaybe() {
    var d = document.documentElement;
    if (S.demo || load('dh_fsask', '1') === '0' || inFullscreen() || !(d.requestFullscreen || d.webkitRequestFullscreen)) { return; }
    try { if (sessionStorage.getItem('dh_fsask_seen')) { return; } sessionStorage.setItem('dh_fsask_seen', '1'); } catch (e) { if (S.fsAsked) { return; } S.fsAsked = true; }
    setTimeout(function () { $('fsask').className = 'overlay top on'; }, 1600);
  }
  $('fsask-go').onclick = function () { $('fsask').className = 'overlay top'; goFullscreen(); };
  $('fsask-later').onclick = function () { $('fsask').className = 'overlay top'; };
  $('fsask-never').onclick = function () { save('dh_fsask', '0'); $('fsask').className = 'overlay top'; };

  // ---------------------------------------------------------------- messages from the PC
  function onMessage(m) {
    switch (m.type) {
      case 'hello_ok':
        S.helloOk = true; retries = 0; denied = false; S.version = m.version || ''; setStatus('online'); sendInfo();
        if (!bootTimer && $('boot').className !== 'gone') { bootTimer = setTimeout(bootHide, 1400); }
        fsAskMaybe();
        break;
      case 'hello_denied':
        denied = true; setStatus('denied'); break;
      case 'layout': S.layout = m; buildNav(); applySleep(); notify('layout'); break;
      case 'home': S.home = m; if (!homeEditing) { buildHome(); } break;
      case 'tiles': S.tiles = m.tiles || []; buildNav(); notify('tiles'); break;
      case 'tile_state': S.lit = m.on || []; notify('tile_state'); break;
      case 'stats':
        S.stats = m;
        S.hist.push({ t: Date.now(), cpu: m.cpu || 0, gpu: typeof m.gpu === 'number' ? m.gpu : null });
        while (S.hist.length > 90 || (S.hist.length > 2 && Date.now() - S.hist[0].t > 75000)) { S.hist.shift(); }
        S.gotData = true; refresh('stats'); notify('stats'); break;
      case 'media':
        S.media = m; S.mediaAt = Date.now(); refresh('media'); notify('media'); syncTicks(); break;
      case 'ping': break;   // the PC's heartbeat: it only proves the link is alive
      case 'events': S.events = m; refresh('events'); notify('events'); break;
      case 'ai': case 'claude':
        S.ai = m; refresh('ai'); notify('ai');
        if (navSig.indexOf('|' + m.provider) < 0) { buildNav(); }
        break;
      case 'net': S.net = m; refresh('net'); notify('net'); break;
      case 'pc_power': S.pcAsleep = !!m.asleep; applySleep(); break;
      case 'alert': showAlert(m); break;
      default:   // anything pages know about (weather, printer, steam, github...)
        if (m.type) { m._at = Date.now(); S.msg[m.type] = m; refresh(m.type); notify(m.type); }
        break;
    }
    if (S.gotData && $('boot').className !== 'gone' && !bootTimer) { bootTimer = setTimeout(bootHide, 250); }
  }

  // What the PC's diagnostics page shows about this phone.
  var infoTimer = null;
  function sendInfo() {
    clearTimeout(infoTimer);
    send({ type: 'info', page: curPage, visible: !document.hidden, mode: effMode(), motion: cfg.motion, reconnects: reconnects,
           viewport: window.innerWidth + 'x' + window.innerHeight, dpr: window.devicePixelRatio || 1,
           up_s: Math.round((Date.now() - T0) / 1000), battery: S.battery || 'n/a', wake: !!wakeSentinel,
           data_age_s: S.lastMsg ? Math.round((Date.now() - S.lastMsg) / 1000) : -1,
           rx_kb: Math.round(S.rxBytes / 102.4) / 10, msgs: S.rxCount, smooth: S.smooth || 'not run',
           heap_mb: window.performance && performance.memory ? Math.round(performance.memory.usedJSHeapSize / 104857.6) / 10 : 'n/a' });
    infoTimer = setTimeout(sendInfo, effMode() === 'normal' ? 30000 : effMode() === 'low' ? 60000 : 120000);
  }

  // ---------------------------------------------------------------- start
  $('pair-go').onclick = function () {
    var v = $('pair-code').value.trim(), m = /[#&]t=([^&\s]+)/.exec(v);
    if (m) { v = decodeURIComponent(m[1]); }
    if (!v) { return; }
    save('dh_token', v); denied = false; $('pair-text').textContent = 'Connecting...'; connect();
  };
  function start(opts) {
    var stage = $('stage'), id, sec;
    if (opts && opts.demo) { S.demo = true; }
    for (id in PAGES) {   // every page gets its own section; registered pages build their own content
      sec = el('section', 'page'); sec.id = 'page-' + id; stage.appendChild(sec);
      if (id === 'home') { buildHomePage(sec); }
      else if (PAGES[id].build) { PAGES[id].build(sec); }
    }
    applyDim(); tickClock(); armClock(); buildHome(); buildNav();
    if (!PAGES[curPage]) { curPage = 'home'; }
    showPage(curPage);
    applyWake();
    if (opts && opts.demo) { bootHide(); setStatus('online'); } else { connect(); }
    setTimeout(placePill, 120);   // after the icon font has loaded the buttons have their final size
    if (document.fonts && document.fonts.ready) { document.fonts.ready.then(placePill); }
  }

  window.DH = {
    S: S, cfg: cfg, send: send, report: report, pages: PAGES, builders: builders, buildNav: buildNav, updateNav: updateNav, wake: touched,
    page: function () { return curPage; }, load: load, save: save, image: image, show: showPage, order: pageOrder, refresh: refresh,
    dispatch: onMessage, start: start,
    home: {   // what homeedit.js needs to change the Home grid
      layout: homeLayout, rebuild: buildHome, fill: fillCard, save: homeSave, cards: function () { return homeCards; },
      unfill: function (card) { widgets = widgets.filter(function (w) { return w.card !== card; }); },
      grid: function () { return $('grid'); }, root: function () { return $('page-home'); },
      forget: function () { drop('dh_home'); homeOverride = null; buildHome(); },
      editing: function (on, layout) { homeEditing = !!on; homeOverride = on ? layout : null; },
      builders: function () { return builders; }, custom: function () { return !!load('dh_home', ''); }
    }
  };
})();
