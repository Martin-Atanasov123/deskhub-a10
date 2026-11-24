/* DeskHub UI toolkit: small building blocks shared by every page. ES5 on purpose (old Android WebViews).
   Motion rules, so it stays smooth on a 2 GB phone: animate only transform, opacity, stroke and width of tiny
   elements; build each page once and update it in place; run nothing continuously except while a loading
   shimmer is on screen. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var UI = { motion: 'full' };   // full | min | off

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS(NS, tag), k;
    for (k in attrs) { if (attrs.hasOwnProperty(k)) { n.setAttribute(k, attrs[k]); } }
    return n;
  }
  function clear(n) { while (n.firstChild) { n.removeChild(n.firstChild); } }
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function icon(name, cls) { return el('span', 'mi' + (cls ? ' ' + cls : ''), name); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  UI.el = el; UI.svg = svg; UI.clear = clear; UI.pad = pad; UI.icon = icon; UI.clamp = clamp;

  // ---------------------------------------------------------------- motion
  UI.setMotion = function (m) {
    UI.motion = m === 'off' || m === 'min' ? m : 'full';
    document.body.className = document.body.className.replace(/\bmotion-\w+/g, '').replace(/\s+$/, '') + ' motion-' + UI.motion;
  };

  // A number that glides to its new value (count-up). Instant when motion is not full.
  UI.tween = function (node, to, fmt, ms) {
    var from = node.__v;
    node.__v = to;
    if (node.__raf) { cancelAnimationFrame(node.__raf); node.__raf = 0; }
    if (typeof from !== 'number' || UI.motion !== 'full' || document.hidden || Math.abs(to - from) < 0.01) {
      node.textContent = fmt(to);
      return;
    }
    var t0 = null, dur = ms || 650;
    function step(t) {
      if (t0 === null) { t0 = t; }
      var k = clamp((t - t0) / dur, 0, 1), e = 1 - Math.pow(1 - k, 3);
      node.textContent = fmt(from + (to - from) * e);
      if (k < 1) { node.__raf = requestAnimationFrame(step); } else { node.__raf = 0; }
    }
    node.__raf = requestAnimationFrame(step);
  };

  // Children rise into place one after another. Safe to call again; it only sets the order.
  UI.rise = function (nodes) {
    var i;
    for (i = 0; i < nodes.length; i++) {
      nodes[i].className += ' rise';
      nodes[i].style.setProperty('--i', String(i));
    }
  };

  // ---------------------------------------------------------------- loading state
  // A card shows a shimmering skeleton until its first data arrives, then its content fades in.
  UI.loading = function (card) { card.className += ' is-loading'; };
  UI.ready = function (card) {
    if (card.className.indexOf('is-loading') >= 0) { card.className = card.className.replace(/\s*is-loading/g, ''); }
  };

  // ---------------------------------------------------------------- components
  UI.bar = function (color) {
    var root = el('div', 'bar'), fill = el('div', 'bar-fill');
    root.appendChild(fill);
    if (color) { fill.style.background = color; }
    return { root: root, fill: fill, set: function (pct, col) {
      fill.style.width = clamp(pct || 0, 0, 100) + '%';
      if (col) { fill.style.background = col; }
    } };
  };

  // An open ring (270 degrees, gap at the bottom) or a full ring. set(percent, color) animates the arc.
  UI.ring = function (full, stroke) {
    var R = 46, C = 2 * Math.PI * R, ARC = full ? C : C * 0.75, sw = stroke || 11;
    var s = svg('svg', { viewBox: '0 0 120 120', 'class': 'ring-svg' });
    var rot = full ? 'rotate(-90 60 60)' : 'rotate(135 60 60)';
    var track = svg('circle', { cx: 60, cy: 60, r: R, fill: 'none', 'stroke-width': sw, 'stroke-linecap': 'round', 'class': 'ring-track',
                                'stroke-dasharray': ARC + ' ' + C, transform: rot });
    var prog = svg('circle', { cx: 60, cy: 60, r: R, fill: 'none', 'stroke-width': sw, 'stroke-linecap': 'round', 'class': 'ring-prog',
                               'stroke-dasharray': '0.01 ' + C, transform: rot });
    s.appendChild(track); s.appendChild(prog);
    return { svg: s, prog: prog, set: function (pct, color) {
      prog.style.strokeDasharray = Math.max(0.01, ARC * clamp(pct || 0, 0, 100) / 100) + ' ' + C;
      if (color) { prog.style.stroke = color; }
    } };
  };

  // Smooth line through points [[x, y], ...] in a 0..w by 0..h box (Catmull-Rom turned into curves).
  UI.curve = function (pts) {
    if (pts.length < 2) { return ''; }
    var d = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1), i;
    for (i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      var c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
      var c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += 'C' + c1x.toFixed(1) + ',' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ',' + c2y.toFixed(1) + ' ' + p2[0].toFixed(1) + ',' + p2[1].toFixed(1);
    }
    return d;
  };

  // Segmented control: [["pc", "PC"], ...]. onPick(value). setValue(v) moves the highlight.
  UI.segmented = function (options, current, onPick) {
    var root = el('div', 'seg'), thumb = el('div', 'seg-thumb'), btns = [], value = current;
    root.appendChild(thumb);
    options.forEach(function (o) {
      var b = el('button', 'seg-btn', o[1]);
      b.onclick = function () { if (value !== o[0]) { api.setValue(o[0]); onPick(o[0]); } };
      btns.push([o[0], b]); root.appendChild(b);
    });
    var api = { root: root, setValue: function (v) {
      value = v;
      var i, idx = 0;
      for (i = 0; i < btns.length; i++) { btns[i][1].className = 'seg-btn' + (btns[i][0] === v ? ' on' : ''); if (btns[i][0] === v) { idx = i; } }
      thumb.style.width = (100 / btns.length) + '%';
      thumb.style.transform = 'translate3d(' + (idx * 100) + '%,0,0)';
    } };
    api.setValue(current);
    return api;
  };

  // ---------------------------------------------------------------- colours
  UI.level = function (pct) { return pct >= 80 ? 'var(--red)' : pct >= 50 ? 'var(--amber)' : 'var(--green)'; };
  UI.tint = function (hex, amount) {   // mix a #rrggbb colour towards white
    var m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) { return '#aeb8b2'; }
    var n = parseInt(m[1], 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    function mix(c) { return Math.round(c + (255 - c) * amount); }
    return 'rgb(' + mix(r) + ',' + mix(g) + ',' + mix(b) + ')';
  };

  // ---------------------------------------------------------------- formatting
  UI.fmtTok = function (n) {
    n = n || 0;
    return n >= 1e9 ? (n / 1e9).toFixed(1) + 'B' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'K' : String(Math.round(n));
  };
  UI.fmtBytes = function (b) {
    b = b || 0;
    return b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? Math.round(b / 1e6) + ' MB' : Math.round(b / 1e3) + ' KB';
  };
  UI.fmtLeft = function (sec) {
    sec = Math.max(0, sec);
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
    return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
  };
  UI.fmtSince = function (sec) {
    sec = Math.max(0, Math.floor(sec));
    var d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
    return d > 0 ? d + 'd ' + h + 'h' : h > 0 ? h + 'h ' + m + 'm' : m + 'm';
  };
  var H12 = (function () { try { return !!new Intl.DateTimeFormat(undefined, { hour: 'numeric' }).resolvedOptions().hour12; } catch (e) { return false; } })();
  UI.hour12 = H12;
  UI.time = function (d) {   // {t: "2:39", ap: "PM" or ""} in the phone's own style (12 or 24 hour)
    var h = d.getHours(), m = pad(d.getMinutes());
    if (!H12) { return { t: pad(h) + ':' + m, ap: '' }; }
    return { t: ((h + 11) % 12 + 1) + ':' + m, ap: h < 12 ? 'AM' : 'PM' };
  };
  UI.timeText = function (d) { var t = UI.time(d); return t.ap ? t.t + ' ' + t.ap : t.t; };
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  UI.days = DAYS; UI.months = MONTHS;
  UI.dayShort = function (i) { return DAYS[i].slice(0, 3); };
  UI.dateLong = function (d) { return DAYS[d.getDay()] + ', ' + MONTHS[d.getMonth()] + ' ' + d.getDate(); };
  UI.ago = function (sec) {
    sec = Math.max(0, sec);
    return sec < 3600 ? Math.max(1, Math.round(sec / 60)) + ' min ago' : sec < 172800 ? Math.round(sec / 3600) + ' h ago' : Math.round(sec / 86400) + ' d ago';
  };
  UI.hours = function (min) { return min >= 60 ? (min / 60).toFixed(min >= 6000 ? 0 : 1) + ' h' : Math.round(min) + ' min'; };

  // ---------------------------------------------------------------- weather
  UI.weather = function (code, day) {
    var amber = '#fbb024', cloud = '#f6cf86', over = '#aab4ec', rain = '#5fd8ee', snow = '#9fe3ff', storm = '#b69cf7', fog = '#9aa8a1';
    if (code === 0) { return day ? { i: 'wb_sunny', t: 'Clear', c: amber } : { i: 'nights_stay', t: 'Clear', c: storm }; }
    if (code === 1) { return day ? { i: 'wb_cloudy', t: 'Mostly clear', c: cloud } : { i: 'nights_stay', t: 'Mostly clear', c: storm }; }
    if (code === 2) { return day ? { i: 'wb_cloudy', t: 'Partly cloudy', c: cloud } : { i: 'nights_stay', t: 'Partly cloudy', c: storm }; }
    if (code === 3) { return { i: 'cloud', t: 'Overcast', c: over }; }
    if (code === 45 || code === 48) { return { i: 'foggy', t: 'Fog', c: fog }; }
    if (code === 56 || code === 57) { return { i: 'grain', t: 'Freezing drizzle', c: rain }; }
    if (code >= 51 && code <= 55) { return { i: 'grain', t: 'Drizzle', c: rain }; }
    if (code === 66 || code === 67) { return { i: 'grain', t: 'Freezing rain', c: rain }; }
    if (code === 61) { return { i: 'grain', t: 'Light rain', c: rain }; }
    if (code === 63) { return { i: 'grain', t: 'Rain', c: rain }; }
    if (code === 65) { return { i: 'grain', t: 'Heavy rain', c: rain }; }
    if (code === 80 || code === 81) { return { i: 'grain', t: 'Showers', c: rain }; }
    if (code === 82) { return { i: 'grain', t: 'Heavy showers', c: rain }; }
    if (code >= 71 && code <= 77) { return { i: 'ac_unit', t: code === 71 ? 'Light snow' : code === 75 ? 'Heavy snow' : 'Snow', c: snow }; }
    if (code === 85 || code === 86) { return { i: 'ac_unit', t: 'Snow showers', c: snow }; }
    if (code >= 95) { return { i: 'thunderstorm', t: code === 95 ? 'Thunderstorm' : 'Storm with hail', c: storm }; }
    return { i: 'cloud', t: 'Unknown', c: over };
  };

  // ---------------------------------------------------------------- provider logos
  // The Claude Code and Codex marks (24x24 paths, from the open-source LobeHub icon set; the marks belong to Anthropic and OpenAI).
  var LOGO_PATH = {
    claude: 'M20.998 10.949H24v3.102h-3v3.028h-1.487V20H18v-2.921h-1.487V20H15v-2.921H9V20H7.488v-2.921H6V20H4.487v-2.921H3V14.05H0V10.95h3V5h17.998v5.949zM6 10.949h1.488V8.102H6v2.847zm10.51 0H18V8.102h-1.49v2.847z',
    codex: 'M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z'
  };
  UI.logo = function (provider, size) {
    var s = svg('svg', { viewBox: '0 0 24 24', 'class': 'logo logo-' + provider, width: size || 24, height: size || 24 });
    s.appendChild(svg('path', { d: LOGO_PATH[provider === 'codex' ? 'codex' : 'claude'], 'fill-rule': 'evenodd' }));
    return s;
  };

  // ---------------------------------------------------------------- smoothness test
  // Measures how evenly the screen redraws while pages slide in and out. done({frames, avg, worst, slow}).
  UI.smoothness = function (switchPage, ids, done) {
    var times = [], last = 0, n = 0, running = true, i;
    function frame(t) {
      if (last) { times.push(t - last); }
      last = t;
      if (running) { requestAnimationFrame(frame); }
    }
    requestAnimationFrame(frame);
    var step = 0, seq = [];
    for (i = 0; i < 2; i++) { seq = seq.concat(ids); }
    (function next() {
      if (step >= seq.length) {
        setTimeout(function () {
          running = false;
          var sum = 0, worst = 0, slow = 0, j;
          for (j = 0; j < times.length; j++) { sum += times[j]; if (times[j] > worst) { worst = times[j]; } if (times[j] > 25) { slow++; } }
          done({ frames: times.length, avg: times.length ? sum / times.length : 0, worst: worst, slow: slow });
        }, 500);
        return;
      }
      switchPage(seq[step++]);
      setTimeout(next, 520);
    })();
    n++;
  };

  window.UI = UI;
})();
