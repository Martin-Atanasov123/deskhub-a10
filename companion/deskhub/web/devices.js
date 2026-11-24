/* 3D printers, Steam games and the GitHub chart, plus their Home widgets. ES5 on purpose.
   Loaded after pages.js. Each page appears only when the PC's [pages] list includes it. */
(function () {
  'use strict';
  var D = window.DH, UI = window.UI, el = UI.el, clear = UI.clear, pad = UI.pad, icon = UI.icon, S = D.S, P = D.pages, B = D.builders;
  function cardOf(cap, extra) { var c = el('div', 'card' + (extra ? ' ' + extra : '')); if (cap) { c.appendChild(el('div', 'cap', cap)); } return c; }
  function deg(v) { return v === null || v === undefined ? '-' : Math.round(v) + '°'; }

  // ================================================================== 3D printers
  var STATE_TEXT = { RUNNING: 'Printing', PREPARE: 'Preparing', PAUSE: 'Paused', FINISH: 'Finished', FAILED: 'Failed', IDLE: 'Idle', OFFLINE: 'Offline' };
  var STATE_COLOR = { RUNNING: 'var(--amber)', PREPARE: 'var(--amber)', PAUSE: 'var(--amber)', FINISH: 'var(--green)', FAILED: 'var(--red)', IDLE: 'var(--muted)', OFFLINE: 'var(--faint)' };
  function busy(p) { return p.state === 'RUNNING' || p.state === 'PREPARE' || p.state === 'PAUSE'; }
  function leftText(min) { return min >= 60 ? Math.floor(min / 60) + 'h ' + (min % 60) + 'm left' : min + 'm left'; }
  P.printer = {
    icon: 'view_in_ar', label: 'Printer', key: 'printer', kinds: ['printer'],
    build: function (root) {
      var page = el('div', 'prn-page'), tabs = el('div'), head = el('div', 'prn-head'), h1 = el('h1', null, '-'), chip = el('span', 'chip', ''), model = el('span', 'sub grow'), body = el('div', 'prn-body');
      tabs.style.marginBottom = '.6rem'; model.style.textAlign = 'right'; head.appendChild(h1); head.appendChild(chip); head.appendChild(model);
      var left = cardOf(null, 'prn-ring'), wrap = el('div', 'ring'), r = UI.ring(false, 10), c = el('div', 'ring-center'), pct = el('div', 'num', '0%'), rem = el('div', 'sub');
      pct.style.fontSize = '2.3rem'; c.appendChild(pct); c.appendChild(rem); wrap.appendChild(r.svg); wrap.appendChild(c);
      var done = el('div', 'done'), doneT = el('div', null, ''), layer = el('div', 'sub'); doneT.style.fontSize = '1.05rem'; done.appendChild(doneT); done.appendChild(layer);
      left.appendChild(wrap); left.appendChild(done); UI.loading(left);
      var right = el('div', 'prn-right'), cJob = cardOf('Printing'), file = el('div'), speed = el('div', 'sub'), err = el('div', 'err');
      file.style.fontSize = '1.4rem'; file.style.fontWeight = '600'; file.style.margin = '.35rem 0 .15rem'; file.className += ' ell'; cJob.appendChild(file); cJob.appendChild(speed); cJob.appendChild(err);
      var cTemps = el('div', 'card'), temps = el('div', 'temps'), tv = {};
      [['Nozzle', 'local_fire_department', 'var(--amber)', 'nozzle'], ['Bed', 'layers', 'var(--blue)', 'bed'], ['Chamber', 'thermostat', 'var(--teal)', 'chamber']].forEach(function (t) {
        var col = el('div'), l = el('div', 'tl'), ic = icon(t[1]), v = el('div', 'tv', '-'), sub = el('div', 'tt', ' '); ic.style.color = t[2];
        l.appendChild(ic); l.appendChild(el('span', null, t[0])); col.appendChild(l); col.appendChild(v); col.appendChild(sub); temps.appendChild(col); tv[t[3]] = { col: col, v: v, sub: sub };
      });
      cTemps.appendChild(temps);
      var cFil = cardOf('Filament'), fil = el('div', 'fil'); cFil.appendChild(fil);
      [cJob, cTemps, cFil].forEach(function (x) { UI.loading(x); right.appendChild(x); });
      body.appendChild(left); body.appendChild(right); page.appendChild(tabs); page.appendChild(head); page.appendChild(body); root.appendChild(page);
      var idx = 0, seg = null, segSig = '', filSig = '';
      P.printer.update = function () {
        var m = S.msg.printer; if (!m) { return; }
        if (!m.printers.length) { head.style.display = body.style.display = 'none'; tabs.innerHTML = ''; var n = el('div', 'sub', 'No printers are set up. On the PC run: uv run deskhub-printers'); tabs.appendChild(n); segSig = ''; return; }
        head.style.display = body.style.display = ''; if (idx >= m.printers.length) { idx = 0; }
        var sig = m.printers.map(function (p) { return p.name; }).join('|');
        if (sig !== segSig) { segSig = sig; clear(tabs); seg = null; if (m.printers.length > 1) { seg = UI.segmented(m.printers.map(function (p, i) { return [i, p.name]; }), idx, function (v) { idx = v; P.printer.update(); }); tabs.appendChild(seg.root); } }
        var p = m.printers[idx]; UI.ready(left); UI.ready(cJob); UI.ready(cTemps); UI.ready(cFil);
        h1.textContent = p.name; chip.textContent = STATE_TEXT[p.state] || p.state; chip.style.color = STATE_COLOR[p.state] || 'var(--muted)'; chip.style.background = 'rgba(255,255,255,.07)'; model.textContent = p.model || '';
        r.set(p.pct, STATE_COLOR[p.state]); UI.tween(pct, p.pct, function (v) { return Math.round(v) + '%'; });
        rem.textContent = busy(p) && p.remaining_min ? leftText(p.remaining_min) : (p.online ? '' : 'offline');
        doneT.textContent = busy(p) && p.remaining_min ? 'Done at ' + UI.timeText(new Date(Date.now() + p.remaining_min * 60000)) : ' ';
        layer.textContent = p.layers ? 'Layer ' + p.layer + ' of ' + p.layers : ' ';
        file.textContent = p.file || (p.online ? 'No job' : 'Offline'); speed.textContent = p.speed ? p.speed + ' speed' : ' '; err.textContent = p.error || '';
        tv.nozzle.v.textContent = deg(p.nozzle); tv.nozzle.sub.textContent = p.nozzle_target ? 'target ' + deg(p.nozzle_target) : ' ';
        tv.bed.v.textContent = deg(p.bed); tv.bed.sub.textContent = p.bed_target ? 'target ' + deg(p.bed_target) : ' ';
        tv.chamber.col.style.display = p.chamber === null || p.chamber === undefined ? 'none' : ''; tv.chamber.v.textContent = deg(p.chamber);
        cFil.style.display = p.ams && p.ams.length ? '' : 'none';
        var fs = JSON.stringify(p.ams); if (fs !== filSig) {
          filSig = fs; clear(fil);
          (p.ams || []).forEach(function (a) { var d = el('div', a.active ? 'on' : ''), dot = el('div', 'dot'); dot.style.background = a.color; d.appendChild(dot); d.appendChild(el('div', null, a.type || '')); fil.appendChild(d); });
        }
        left.style.opacity = p.online ? '' : '.55';
      };
      P.printer.update();
    }
  };
  B.printer = function (card) {
    card.appendChild(el('div', 'cap', '3D printer')); var row = el('div', 'row'), nm = el('div', 'evt grow ell', '-'), chip = el('span', 'chip', ''), bar = UI.bar('var(--amber)'), sub = el('div', 'evs', ' ');
    row.style.margin = '.4rem 0 .5rem'; row.appendChild(nm); row.appendChild(chip); card.appendChild(row); card.appendChild(bar.root); card.appendChild(sub); UI.loading(card);
    return { kind: 'printer', update: function () {
      var m = S.msg.printer; if (!m || !m.printers.length) { return; } UI.ready(card);
      var p = m.printers[0], i; for (i = 0; i < m.printers.length; i++) { if (busy(m.printers[i])) { p = m.printers[i]; break; } }
      nm.textContent = p.name; chip.textContent = STATE_TEXT[p.state] || p.state; chip.style.color = STATE_COLOR[p.state]; bar.set(p.pct, STATE_COLOR[p.state]);
      sub.textContent = p.online ? p.pct + '%' + (busy(p) && p.remaining_min ? '  •  ' + leftText(p.remaining_min) : '') : 'Offline';
    } };
  };

  // ================================================================== Steam games
  function sessionSeconds(st) { return (st.playing.session_s || 0) + (Date.now() - (st._at || Date.now())) / 1000; }
  P.games = {
    icon: 'sports_esports', label: 'Games', key: 'games', kinds: ['steam'],
    build: function (root) {
      var page = el('div', 'games-page'), now = el('div', 'card now-card'), hdr = el('div', 'hdr'), himg = el('img'); hdr.appendChild(himg);
      var txt = el('div', 'grow'), cap = el('div', 'cap', 'Now playing'), nm = el('div', 'nm ell'), pf = el('div', 'pf'), meta = el('div', 'sub');
      cap.style.color = 'var(--green)'; txt.appendChild(cap); txt.appendChild(nm); txt.appendChild(pf); txt.appendChild(meta); now.appendChild(hdr); now.appendChild(txt); UI.loading(now);
      var rec = el('div', 'card rec-card'), rcap = el('div', 'cap', 'Recent  •  tap to play'), row = el('div', 'rec-row'); rec.appendChild(rcap); rec.appendChild(row); UI.loading(rec);
      var empty = el('div', 'sub', ''); empty.style.display = 'none';
      var confirm = el('div', 'confirm'); page.appendChild(now); page.appendChild(rec); page.appendChild(empty); page.appendChild(confirm); root.appendChild(page);
      var recSig = '', playId = -1, tick = null, covers = {};
      function ask(g) {
        clear(confirm); confirm.className = 'confirm on'; var t = el('span', 'grow ell', 'Launch ' + g.name + ' on the PC?'), go = el('button', 'btn', 'Launch'), no = el('button', 'btn ghost', 'Cancel');
        go.onclick = function () { D.send({ type: 'steam_launch', appid: g.appid }); confirm.className = 'confirm'; }; no.onclick = function () { confirm.className = 'confirm'; };
        confirm.appendChild(t); confirm.appendChild(go); confirm.appendChild(no);
      }
      function time() { var st = S.msg.steam; if (st && st.playing) { pf.textContent = 'Playing for ' + UI.fmtLeft(sessionSeconds(st)); } }
      P.games.update = function () {
        var st = S.msg.steam; if (!st) { return; } UI.ready(now); UI.ready(rec);
        if (!st.found) { now.style.display = rec.style.display = 'none'; empty.style.display = ''; empty.textContent = 'Steam was not found on this PC, and no games are set in config.toml.'; return; }
        now.style.display = rec.style.display = ''; empty.style.display = 'none'; confirm.className = 'confirm';
        if (st.playing) {
          cap.textContent = 'Now playing'; nm.textContent = st.playing.name; time();
          meta.textContent = (st.playing.total_min ? UI.hours(st.playing.total_min) + ' played' : '') + (st.friends && st.friends.length ? '  •  ' + st.friends.length + ' friend' + (st.friends.length > 1 ? 's' : '') + ' in game' : '');
          if (st.playing.appid !== playId) { playId = st.playing.appid; D.image(himg, '/steam/' + playId + '/header'); }
        } else { cap.textContent = 'Not playing'; nm.textContent = st.recent && st.recent[0] ? 'Last: ' + st.recent[0].name : '-'; pf.textContent = ''; meta.textContent = ''; playId = -1; D.image(himg, ''); }
        var sig = (st.recent || []).map(function (g) { return g.appid; }).join(',');
        if (sig !== recSig) {
          recSig = sig; clear(row); covers = {};
          (st.recent || []).forEach(function (g) {
            var b = el('button', 'rec'), im = el('div', 'im'), img = el('img'), hrs = el('div', 'hrs'), n = el('div', 'nm ell'); im.appendChild(img); im.appendChild(hrs); b.appendChild(im); b.appendChild(n);
            b.onclick = function () { ask(g); }; row.appendChild(b); covers[g.appid] = { hrs: hrs, n: n }; D.image(img, '/steam/' + g.appid + '/cover');
          });
          UI.rise([].slice.call(row.children));
        }
        (st.recent || []).forEach(function (g) { var c = covers[g.appid]; if (c) { c.hrs.textContent = g.total_min ? UI.hours(g.total_min).replace(' min', ' m').replace(' h', ' h') : ''; c.hrs.style.display = g.total_min ? '' : 'none'; c.n.textContent = g.name; } });
      };
      P.games.sync = function () {   // the "playing for" clock moves only while the page is open
        var need = D.page() === 'games' && !document.hidden;
        if (need && !tick) { tick = setInterval(time, 15000); } else if (!need && tick) { clearInterval(tick); tick = null; }
      };
      P.games.update();
    }
  };
  B.game = function (card) {
    card.appendChild(el('div', 'cap', 'Steam')); var row = el('div', 'row'), ic = icon('sports_esports'), box = el('div', 'grow'), t = el('div', 'evt ell', '-'), s = el('div', 'evs ell');
    ic.style.fontSize = '2.2rem'; ic.style.color = 'var(--green)'; ic.style.marginRight = '.7rem'; row.style.marginTop = '.4rem'; box.appendChild(t); box.appendChild(s); row.appendChild(ic); row.appendChild(box); card.appendChild(row); UI.loading(card);
    return { kind: 'steam', update: function () {
      var st = S.msg.steam; if (!st) { return; } UI.ready(card);
      if (!st.found) { t.textContent = 'Steam not found'; s.textContent = ''; return; }
      if (st.playing) { t.textContent = st.playing.name; s.textContent = 'Playing for ' + UI.fmtLeft(sessionSeconds(st)); }
      else { t.textContent = 'Not playing'; s.textContent = st.recent && st.recent[0] ? 'Last: ' + st.recent[0].name : ''; }
    } };
  };

  // ================================================================== GitHub contributions
  var GREEN = ['#1a2420', '#0e4429', '#006d32', '#26a641', '#39d353'];
  var BLUE = ['#1a2420', '#1f3a6b', '#2c57a8', '#3b73e0', '#6aa0ff'];
  // The year as a grid of days. weeks: how many week columns to show (the newest ones); labels: month and weekday names.
  function heat(g, weeks, labels) {
    var cell = 10, gap = 2, step = cell + gap, left = labels ? 24 : 0, top = labels ? 13 : 0;
    var lv = g.levels || '', total = Math.ceil((g.start_wday + lv.length) / 7), first = Math.max(0, total - weeks), cols = total - first, i;
    var s = UI.svg('svg', { viewBox: '0 0 ' + (left + cols * step - gap) + ' ' + (top + 7 * step - gap), 'class': 'heat-svg', 'shape-rendering': 'crispEdges', preserveAspectRatio: 'xMidYMid meet' });
    var colors = g.accent ? BLUE : GREEN;
    for (i = 0; i < lv.length; i++) {
      var col = Math.floor((i + g.start_wday) / 7), row = (i + g.start_wday) % 7; if (col < first) { continue; }
      var attrs = { x: left + (col - first) * step, y: top + row * step, width: cell, height: cell, rx: 2, fill: colors[parseInt(lv.charAt(i), 10)] || colors[0] };
      if (i === lv.length - 1) { attrs.stroke = '#e8efe9'; attrs['stroke-width'] = 1; }
      s.appendChild(UI.svg('rect', attrs));
    }
    if (labels) {
      (g.months || []).forEach(function (m) { if (m[0] < first) { return; } var t = UI.svg('text', { x: left + (m[0] - first) * step, y: 9, 'font-size': 8, fill: '#8d9b94', 'font-family': 'Inter, sans-serif' }); t.textContent = m[1]; s.appendChild(t); });
      [[1, 'Mon'], [3, 'Wed'], [5, 'Fri']].forEach(function (d) { var t = UI.svg('text', { x: 0, y: top + d[0] * step + 8, 'font-size': 8, fill: '#8d9b94', 'font-family': 'Inter, sans-serif' }); t.textContent = d[1]; s.appendChild(t); });
    }
    return s;
  }
  P.github = {
    icon: 'commit', label: 'GitHub', key: 'github', kinds: ['github'],
    build: function (root) {
      var page = el('div', 'gh-page'), year = cardOf(null, 'gh-year'), head = el('div', 'head'), stat = el('span'), holder = el('div');
      head.appendChild(el('span', 'cap', 'Last year')); head.appendChild(stat); year.appendChild(head); year.appendChild(holder); UI.loading(year);
      var row = el('div', 'gh-row'), cStreak = cardOf('Streak'), cWeek = cardOf('This week'), cRepos = cardOf('Top repos');
      var sn = el('div', 'streak-n', '-'), k1 = el('div', 'kvs'), k2 = el('div'), k3 = el('div'); k1.appendChild(k2); k1.appendChild(k3); cStreak.appendChild(sn); cStreak.appendChild(k1);
      var wn = el('div', 'week-n', '-'), wbars = el('div', 'week-bars'), wcols = [], i;
      cWeek.appendChild(wn); cWeek.appendChild(wbars);
      for (i = 0; i < 7; i++) { var w = el('div', 'wk'), pair = el('div', 'pair'), b1 = el('div', 'b last'), b2 = el('div', 'b now'), l = el('div', 'l', 'SMTWTFS'.charAt(i)); pair.appendChild(b1); pair.appendChild(b2); w.appendChild(pair); w.appendChild(l); wbars.appendChild(w); wcols.push({ w: w, b1: b1, b2: b2 }); }
      var rrows = []; for (i = 0; i < 4; i++) { var r = el('div', 'repo'), t = el('div', 'top'), n = el('span'), c = el('span'), bar = UI.bar(); t.appendChild(n); t.appendChild(c); r.appendChild(t); r.appendChild(bar.root); r.style.display = 'none'; cRepos.appendChild(r); rrows.push({ r: r, n: n, c: c, bar: bar }); }
      [cStreak, cWeek, cRepos].forEach(function (x) { UI.loading(x); row.appendChild(x); });
      page.appendChild(year); page.appendChild(row); root.appendChild(page); var sig = '';
      P.github.update = function () {
        var g = S.msg.github; if (!g) { return; } UI.ready(year); UI.ready(cStreak); UI.ready(cWeek); UI.ready(cRepos);
        var k = g.kinds || {}; stat.textContent = g.total.toLocaleString() + ' contributions' + (k.commits ? '  •  ' + k.commits + ' commits' : '') + (k.private ? '  •  ' + k.private + ' private' : '') + (k.issues ? '  •  ' + k.issues + ' issues' : '');
        var s2 = g.levels + g.start_wday; if (s2 !== sig) { sig = s2; clear(holder); holder.appendChild(heat(g, 54, true)); }
        sn.innerHTML = g.streak + '<small>days</small>'; k2.innerHTML = '<span>Longest</span><span>' + (g.longest || 0) + ' days</span>'; k3.innerHTML = '<span>Best day</span><span>' + g.best + (g.best_date ? ' on ' + g.best_date : '') + '</span>';
        var diff = g.week - g.last_week; wn.innerHTML = g.week + '<small>' + (diff >= 0 ? '+' : '') + diff + ' vs last week</small>'; wn.lastChild.style.color = diff >= 0 ? 'var(--green)' : 'var(--red)';
        var cur = g.week_days || [], prev = g.last_week_days || [], max = 1, j; for (j = 0; j < 7; j++) { max = Math.max(max, cur[j] || 0, prev[j] || 0); }
        var today = cur.length - 1;
        for (j = 0; j < 7; j++) { wcols[j].b1.style.height = (prev[j] ? Math.max(4, prev[j] / max * 100) : 3) + '%'; wcols[j].b2.style.height = (cur[j] ? Math.max(4, cur[j] / max * 100) : 3) + '%'; wcols[j].w.className = 'wk' + (j === today ? ' today' : ''); }
        var rs = g.repos || [], rmax = rs.length ? rs[0].count || 1 : 1;
        rrows.forEach(function (x, n2) { var rp = rs[n2]; x.r.style.display = rp ? '' : 'none'; if (rp) { x.n.textContent = rp.name; x.c.textContent = rp.count; x.bar.set(rp.count / rmax * 100); } });
      };
      P.github.update();
    }
  };
  B.github = function (card, it) {
    card.className += ' w-github'; var holder = el('div', 'heat'), side = el('div', 'side'), t = el('div', 'num', '-'), s = el('div', 'sub');
    t.style.fontSize = '1.9rem'; t.style.margin = '.35rem 0 .25rem'; side.appendChild(el('div', 'cap', 'GitHub')); side.appendChild(t); side.appendChild(s); card.appendChild(holder); card.appendChild(side); UI.loading(card);
    var sig = '';
    return { kind: 'github', update: function () {
      var g = S.msg.github; if (!g) { return; } UI.ready(card);
      var s2 = g.levels + it.w; if (s2 !== sig) { sig = s2; clear(holder); holder.appendChild(heat(g, Math.min(54, it.w * 9 + 4), false)); }
      t.textContent = g.total.toLocaleString(); s.textContent = g.streak + '-day streak';
    } };
  };
})();
