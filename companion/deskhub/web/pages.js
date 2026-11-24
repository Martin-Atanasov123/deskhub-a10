/* Stats, AI (Claude and Codex), Calendar, Weather, Media, Shortcut keys and Timer, plus their Home widgets.
   ES5 on purpose. Every page is built once and then updated in place, so values glide instead of flickering. */
(function () {
  'use strict';
  var D = window.DH, UI = window.UI, el = UI.el, clear = UI.clear, pad = UI.pad, icon = UI.icon, S = D.S, P = D.pages, B = D.builders;
  function pctText(v) { return Math.round(v) + '%'; }
  function deg(v) { return Math.round(v) + '°'; }
  function setCls(node, cls) { node.className = cls; }
  function rate(kb) { return kb >= 1024 ? (kb / 1024).toFixed(1) + ' MB/s' : Math.round(kb) + ' KB/s'; }
  function cardOf(cap, extra) { var c = el('div', 'card' + (extra ? ' ' + extra : '')); if (cap) { c.appendChild(el('div', 'cap', cap)); } return c; }
  function hourLabel(d) { var h = d.getHours(); return UI.hour12 ? ((h + 11) % 12 + 1) + ' ' + (h < 12 ? 'AM' : 'PM') : pad(h) + ':00'; }

  // ================================================================== Stats: PC and Internet
  var sp = null;
  function gauge(name, color) {
    var card = el('div', 'card gauge'), wrap = el('div', 'ring'), ring = UI.ring(false, 10), c = el('div', 'ring-center'), n = el('div', 'num', '-');
    ring.prog.style.stroke = color; c.appendChild(n); wrap.appendChild(ring.svg); wrap.appendChild(c);
    var nm = el('div', 'name', name), sub = el('div', 'sub', ' ');
    card.appendChild(wrap); card.appendChild(nm); card.appendChild(sub); UI.loading(card);
    return { card: card, set: function (pct, text) { UI.ready(card); ring.set(pct); UI.tween(n, pct, pctText); sub.textContent = text || ' '; } };
  }
  // A smooth line chart of values over time. series: [{key, color, path}], window in ms.
  function plot(colors, maxV) {
    var wrap = el('div', 'plot'), s = UI.svg('svg', { viewBox: '0 0 100 40', preserveAspectRatio: 'none' }), i, paths = [];
    for (i = 1; i <= 3; i++) { s.appendChild(UI.svg('line', { x1: 0, x2: 100, y1: i * 10, y2: i * 10, 'class': 'grid-line' })); }
    colors.forEach(function (c) { var p = UI.svg('path', { 'class': 'line', stroke: c, d: '' }); s.appendChild(p); paths.push(p); });
    wrap.appendChild(s);
    return { root: wrap, paths: paths };
  }
  P.stats = {
    icon: 'auto_graph', label: 'Stats', key: 'stats', kinds: ['stats', 'net', 'layout'],
    build: function (root) {
      var page = el('div', 'stats-page'), top = el('div'), hasNet = false;
      var seg = UI.segmented([['pc', 'PC'], ['net', 'Internet']], 'pc', function (v) { show(v); });
      top.appendChild(seg.root); page.appendChild(top);
      var views = el('div', 'stats-view'), pc = el('div', 'sview on'), net = el('div', 'sview');
      // PC view
      var gauges = el('div', 'gauges'), g = { cpu: gauge('CPU', 'var(--blue)'), gpu: gauge('GPU', 'var(--teal)'), ram: gauge('RAM', 'var(--purple)'), vram: gauge('VRAM', 'var(--pink)') };
      ['cpu', 'gpu', 'ram', 'vram'].forEach(function (k) { gauges.appendChild(g[k].card); });
      var chart = cardOf(null, 'chart-card'), head = el('div', 'head'), left = el('div', 'row');
      left.appendChild(el('span', 'cap', 'Last minute'));
      var l1 = el('span', 'legend'), l2 = el('span', 'legend'); l1.innerHTML = '<i style="background:var(--blue)"></i>CPU'; l2.innerHTML = '<i style="background:var(--teal)"></i>GPU';
      left.appendChild(l1); left.appendChild(l2);
      var speeds = el('div', 'sub', ''); head.appendChild(left); head.appendChild(speeds);
      var pl = plot(['var(--blue)', 'var(--teal)']), foot = el('div', 'foot'), names = el('span'), disk = el('span');
      foot.appendChild(names); foot.appendChild(disk);
      chart.appendChild(head); chart.appendChild(pl.root); chart.appendChild(foot); pc.appendChild(gauges); pc.appendChild(chart);
      // Internet view
      var ntop = el('div', 'net-top'), cLat = cardOf('Latency'), cSt = cardOf('Status'), cData = cardOf('Data used');
      var latN = el('div', 'big', '-'), latSub = el('div', 'sub'), stN = el('div', 'big', '-'), stSub = el('div', 'sub'), kv = el('div', 'kvs');
      cLat.appendChild(latN); cLat.appendChild(latSub); cSt.appendChild(stN); cSt.appendChild(stSub); cData.appendChild(kv);
      var kToday = el('div'), kMonth = el('div'); kv.appendChild(kToday); kv.appendChild(kMonth);
      [cLat, cSt, cData].forEach(function (c) { UI.loading(c); ntop.appendChild(c); });
      var nchart = cardOf(null, 'chart-card'), nh = el('div', 'head'), nmax = el('span', 'sub'); nh.appendChild(el('span', 'cap', 'Latency, last 2 minutes')); nh.appendChild(nmax);
      var npl = plot(['var(--teal)']); nchart.appendChild(nh); nchart.appendChild(npl.root);
      var sp2 = cardOf(null, 'speed'), dn = el('div', 'big'), up = el('div', 'big'), spsub = el('div', 'sub'), now = el('div', 'sub'), run = el('button', 'btn', 'Run test');
      var colA = el('div', 'grow'), r1 = el('div', 'row'); dn.innerHTML = '<span class="c-green">↓</span> <span class="v">-</span>'; up.innerHTML = '<span class="c-blue">↑</span> <span class="v">-</span>';
      up.style.marginLeft = '1.4rem'; r1.appendChild(dn); r1.appendChild(up); colA.appendChild(r1); colA.appendChild(spsub);
      var colB = el('div'); colB.style.textAlign = 'right'; colB.appendChild(now); run.style.marginTop = '.4rem'; colB.appendChild(run);
      sp2.appendChild(colA); sp2.appendChild(colB); UI.loading(sp2);
      run.onclick = function () { D.send({ type: 'speedtest' }); };
      net.appendChild(ntop); net.appendChild(nchart); net.appendChild(sp2);
      views.appendChild(pc); views.appendChild(net); page.appendChild(views); root.appendChild(page);

      var view = 'pc', raf = 0;
      function show(v) { view = v; setCls(pc, 'sview' + (v === 'pc' ? ' on' : '')); setCls(net, 'sview' + (v === 'net' ? ' on' : '')); seg.setValue(v); drawPc(); drawNet(); P.stats.sync(); }
      function drawPc() {
        var now = Date.now(), win = 60000, pts = { cpu: [], gpu: [] };
        S.hist.forEach(function (h) {
          var x = (h.t - (now - win)) / win * 100; if (x < -5) { return; }
          pts.cpu.push([x, 38.5 - h.cpu * 0.37]); if (h.gpu !== null) { pts.gpu.push([x, 38.5 - h.gpu * 0.37]); }
        });
        pl.paths[0].setAttribute('d', UI.curve(pts.cpu)); pl.paths[1].setAttribute('d', UI.curve(pts.gpu));
      }
      function drawNet() {
        var n = S.net; if (!n || !n.hist) { return; }
        var h = n.hist, max = 50, i, pts = [];
        for (i = 0; i < h.length; i++) { if (h[i] > max) { max = h[i]; } }
        for (i = 0; i < h.length; i++) { if (h[i] >= 0) { pts.push([i * 100 / Math.max(1, h.length - 1), 38 - h[i] / max * 34]); } }
        npl.paths[0].setAttribute('d', UI.curve(pts)); nmax.textContent = 'max ' + Math.round(max) + ' ms';
      }
      function live() { drawPc(); raf = requestAnimationFrame(live); }
      P.stats.sync = function () {   // the chart scrolls every frame only while it is on screen, in Normal power and full motion
        var need = D.page() === 'stats' && view === 'pc' && UI.motion === 'full' && D.cfg.mode === 'normal' && !document.hidden;
        if (need && !raf) { raf = requestAnimationFrame(live); } else if (!need && raf) { cancelAnimationFrame(raf); raf = 0; }
      };
      P.stats.update = function (kind) {
        if (kind === 'layout') {
          var l = S.layout && S.layout.pages; hasNet = !l || l.indexOf('network') >= 0;
          seg.root.style.display = hasNet ? '' : 'none'; if (!hasNet && view === 'net') { show('pc'); } return;
        }
        var s = S.stats, n = S.net;
        if (s) {
          g.cpu.set(s.cpu);
          var ramPct = s.ram_total ? s.ram_used / s.ram_total * 100 : 0; g.ram.set(ramPct, s.ram_used.toFixed(1) + ' / ' + s.ram_total + ' GB');
          var hasGpu = typeof s.gpu === 'number'; g.gpu.card.style.display = hasGpu ? '' : 'none'; g.vram.card.style.display = hasGpu && s.vram_total ? '' : 'none';
          gauges.style.gridTemplateColumns = 'repeat(' + (hasGpu ? (s.vram_total ? 4 : 3) : 2) + ', minmax(0, 1fr))';
          if (hasGpu) { g.gpu.set(s.gpu, s.gpu_temp > 0 ? Math.round(s.gpu_temp) + '°C' : ''); if (s.vram_total) { g.vram.set(s.vram_used / s.vram_total * 100, s.vram_used.toFixed(1) + ' / ' + s.vram_total + ' GB'); } }
          speeds.innerHTML = '↓ ' + rate(s.net_down || 0) + '&nbsp;&nbsp; ↑ ' + rate(s.net_up || 0);
          names.textContent = (s.cpu_name || '') + (s.gpu_name ? '  /  ' + s.gpu_name : ''); disk.textContent = 'Disk ' + Math.round(s.disk || 0) + '% used';
          if (!raf) { drawPc(); }
          if (n) { now.textContent = 'Now ↓ ' + ((s.net_down || 0) * 8 / 1024).toFixed(1) + ' ↑ ' + ((s.net_up || 0) * 8 / 1024).toFixed(1) + ' Mbps'; }
        }
        if (n) {
          UI.ready(cLat); UI.ready(cSt); UI.ready(cData); UI.ready(sp2);
          UI.tween(latN, n.latency_ms >= 0 ? n.latency_ms : 0, function (v) { return n.latency_ms >= 0 ? Math.round(v) + ' ms' : '-'; });
          latSub.textContent = 'Jitter ' + (n.jitter_ms || 0).toFixed(1) + ' ms • Loss ' + (n.loss_pct || 0) + '%';
          stN.textContent = n.online ? 'Online' : 'Offline'; stN.className = 'big ' + (n.online ? 'c-green' : 'c-red');
          var nowS = Date.now() / 1000;
          stSub.textContent = (n.up_since ? 'Up ' + UI.fmtSince(nowS - n.up_since) : '') + (n.last_drop && n.last_drop.at ? ' • Last drop ' + UI.fmtSince(nowS - n.last_drop.at) + ' ago' : '');
          kToday.innerHTML = '<span>Today</span><span>' + UI.fmtBytes(n.today_bytes) + '</span>'; kMonth.innerHTML = '<span>This month</span><span>' + UI.fmtBytes(n.month_bytes) + '</span>';
          if (n.speed) {
            dn.lastChild.textContent = Math.round(n.speed.down_mbps) + ' Mbps'; up.lastChild.textContent = Math.round(n.speed.up_mbps) + ' Mbps';
            spsub.textContent = 'Ping ' + Math.round(n.speed.ping_ms) + ' ms • tested ' + UI.ago(nowS - n.speed.at);
          } else { spsub.textContent = 'No speed test yet'; }
          run.disabled = !!n.testing; run.textContent = n.testing ? 'Testing...' : 'Run test';
          drawNet();
        }
      };
      P.stats.show = function () { drawPc(); drawNet(); P.stats.sync(); };
      P.stats.hide = function () { P.stats.sync(); };
      P.stats.update('layout');
    }
  };
  B.stats = function (card, it) {
    var rows = [['CPU', 'var(--blue)'], ['GPU', 'var(--teal)'], ['RAM', 'var(--purple)']].map(function (r) {
      var row = el('div', 'srow'), bar = UI.bar(r[1]), val = el('span', 'val', '-');
      row.appendChild(el('span', 'lab', r[0])); row.appendChild(bar.root); row.appendChild(val); card.appendChild(row);
      return { row: row, bar: bar, val: val };
    });
    card.className += ' w-stats'; card.style.display = 'flex'; card.style.flexDirection = 'column'; card.style.justifyContent = 'center'; UI.loading(card);
    return { kind: 'stats', update: function () {
      var s = S.stats; if (!s) { return; } UI.ready(card);
      var ram = s.ram_total ? s.ram_used / s.ram_total * 100 : 0, vals = [s.cpu, s.gpu, ram];
      rows[1].row.style.display = typeof s.gpu === 'number' ? '' : 'none';
      rows.forEach(function (r, i) { var v = vals[i] || 0; r.bar.set(v); UI.tween(r.val, v, pctText); });
    } };
  };
  B.net = function (card) {
    card.appendChild(el('div', 'cap', 'Internet')); var big = el('div', 'num', '-'), sub = el('div', 'sub'); big.style.fontSize = '1.5rem'; big.style.margin = '.4rem 0 .2rem';
    card.appendChild(big); card.appendChild(sub); UI.loading(card);
    return { kind: 'net', update: function () {
      var n = S.net; if (!n) { return; } UI.ready(card);
      big.textContent = n.online ? 'Online' : 'Offline'; big.className = 'num ' + (n.online ? 'c-green' : 'c-red');
      sub.textContent = (n.latency_ms >= 0 ? Math.round(n.latency_ms) + ' ms' : 'no reply') + (n.loss_pct ? ' • ' + n.loss_pct + '% loss' : '');
    } };
  };

  // ================================================================== AI: Claude Code and Codex (one layout, two colours)
  function limitCard(title) {
    var card = el('div', 'card'), pct = el('div', 'big-pct', '-'), bar = UI.bar('var(--green)'), note = el('div', 'ai-note', ' ');
    card.appendChild(el('div', 'cap', title)); card.appendChild(pct); card.appendChild(bar.root); card.appendChild(note); UI.loading(card);
    return { card: card, set: function (w, noteText, missing) {
      UI.ready(card);
      if (w) { var c = UI.level(w.pct); pct.style.color = c; bar.set(w.pct, c); UI.tween(pct, w.pct, pctText); note.textContent = noteText; }
      else { pct.style.color = 'var(--faint)'; pct.__v = undefined; pct.textContent = '—'; bar.set(0); note.textContent = missing; }
    } };
  }
  function resetWeekly(sec) { var d = new Date(sec * 1000); return 'Resets ' + UI.dayShort(d.getDay()) + ' ' + UI.timeText(d); }
  P.ai = {
    icon: 'smart_toy', label: 'AI', key: 'ai', kinds: ['ai'],
    navIcon: function () { return UI.logo(S.ai && S.ai.provider === 'codex' ? 'codex' : 'claude', 26); },
    badge: function () { return !!S.alertId; },
    build: function (root) {
      var page = el('div', 'ai-page prov-claude'), top = el('div', 'ai-top');
      var c5 = limitCard('5-hour limit'), cw = limitCard('Weekly limit'), ct = cardOf(null), kvs = el('div', 'kvs'), kv = {};
      // Which agent this page shows: the PC's "auto" (whichever was used last), or Claude Code, or Codex.
      var th = el('div', 'ai-thead'), sw = UI.segmented([['auto', 'Auto'], ['claude', 'Claude'], ['codex', 'Codex']], D.load('dh_agent', '') || 'auto', function (v) {
        D.save('dh_agent', v); D.send({ type: 'ai_agent', agent: v });
      });
      th.appendChild(el('span', 'cap', 'Today')); sw.root.className += ' ai-switch'; th.appendChild(sw.root); ct.appendChild(th);
      ['Tokens', 'Output', 'Messages', 'Last hour'].forEach(function (k) { var r = el('div'); r.appendChild(el('span', null, k)); kv[k] = el('span', null, '-'); r.appendChild(kv[k]); kvs.appendChild(r); });
      ct.appendChild(kvs); UI.loading(ct);
      top.appendChild(c5.card); top.appendChild(cw.card); top.appendChild(ct);
      var bottom = el('div', 'ai-bottom'), chart = cardOf(null, 'ai-chart'), head = el('div', 'head'), peak = el('span', 'sub', '');
      head.appendChild(el('span', 'cap', 'Last 7 days')); head.appendChild(peak); chart.appendChild(head);
      var days = el('div', 'days'), cols = [], i;
      for (i = 0; i < 7; i++) { var d = el('div', 'day'), col = el('div', 'col'), lbl = el('div', 'lbl', ''); d.appendChild(col); d.appendChild(lbl); days.appendChild(d); cols.push({ col: col, lbl: lbl }); }
      chart.appendChild(days); UI.loading(chart);
      var models = cardOf('Models today', 'ai-models'), mrows = [];
      for (i = 0; i < 4; i++) {
        var row = el('div', 'mrow'), t = el('div', 'top'), nm = el('span'), vl = el('span'), bar = UI.bar();
        t.appendChild(nm); t.appendChild(vl); row.appendChild(t); row.appendChild(bar.root); row.style.display = 'none'; models.appendChild(row); mrows.push({ row: row, nm: nm, vl: vl, bar: bar });
      }
      UI.loading(models);
      bottom.appendChild(chart); bottom.appendChild(models); page.appendChild(top); page.appendChild(bottom); root.appendChild(page);
      P.ai.update = function () {
        var a = S.ai; if (!a) { return; }
        var codex = a.provider === 'codex'; setCls(page, 'ai-page ' + (codex ? 'prov-codex' : 'prov-claude'));
        sw.setValue(a.agent || 'auto');
        var lim = a.limits || {}, now = Date.now() / 1000, miss = codex ? 'Not reported' : 'Needs the Claude Code status line';
        c5.set(lim.five_hour, lim.five_hour && lim.five_hour.reset ? 'Resets in ' + UI.fmtLeft(lim.five_hour.reset - now) : '', miss);
        cw.set(lim.seven_day, lim.seven_day && lim.seven_day.reset ? resetWeekly(lim.seven_day.reset) : '', ' ');
        UI.ready(ct); UI.ready(chart); UI.ready(models);
        var t = a.today || {};
        kv.Tokens.textContent = UI.fmtTok(t.tokens); kv.Output.textContent = UI.fmtTok(t.output); kv.Messages.textContent = String(t.messages || 0); kv['Last hour'].textContent = UI.fmtTok(a.last_hour);
        var ds = a.days || [], max = 1, k;
        for (k = 0; k < ds.length; k++) { if (ds[k] > max) { max = ds[k]; } }
        var today = new Date();
        for (k = 0; k < 7; k++) {
          var v = ds[ds.length - 7 + k] || 0, dn = new Date(today.getTime() - (6 - k) * 86400000);
          cols[k].col.style.height = (v ? Math.max(3, v / max * 100) : 0) + '%'; cols[k].lbl.textContent = k === 6 ? 'Today' : UI.dayShort(dn.getDay());
        }
        peak.textContent = 'peak ' + UI.fmtTok(max === 1 && !ds.length ? 0 : max) + ' tokens';
        var ms = (a.models || []).slice().sort(function (x, y) { return y.tokens - x.tokens; }), mmax = ms.length ? ms[0].tokens || 1 : 1;
        mrows.forEach(function (r, j) {
          var m = ms[j]; r.row.style.display = m ? '' : 'none';
          if (m) { r.nm.textContent = m.name; r.vl.textContent = UI.fmtTok(m.tokens); r.bar.set(m.tokens / mmax * 100); }
        });
      };
      P.ai.update();
    }
  };
  B.claude = function (card, it) {
    card.className += ' w-ai' + (it && it.w < 3 ? ' narrow' : '') + (it && it.w < 2 ? ' tiny' : ''); var tile = el('div', 'logo-tile'), lims = el('div', 'lims');
    function block(t) { var b = el('div', 'lim'), h = el('div', 'lim-head'), cap = el('span', 'cap', t), pct = el('span', 'lim-pct', '-'), bar = UI.bar('var(--green)'), note = el('div', 'lim-note', ' ');
      h.appendChild(cap); h.appendChild(pct); b.appendChild(h); b.appendChild(bar.root); b.appendChild(note); lims.appendChild(b); return { cap: cap, pct: pct, bar: bar, note: note }; }
    var b5 = block('5-hour limit'), bw = block('Weekly limit');
    card.appendChild(tile); card.appendChild(lims); UI.loading(card);
    return { kind: 'ai', update: function () {
      var a = S.ai; if (!a) { return; } UI.ready(card);
      var codex = a.provider === 'codex'; clear(tile); tile.className = 'logo-tile' + (codex ? ' codex' : ''); tile.appendChild(UI.logo(codex ? 'codex' : 'claude', 26));
      var lim = a.limits || {}, now = Date.now() / 1000;
      function fill(b, w, noteText) {
        if (w) { var c = UI.level(w.pct); b.pct.style.color = c; b.bar.set(w.pct, c); UI.tween(b.pct, w.pct, pctText); b.note.textContent = noteText; }
        else { b.pct.style.color = 'var(--faint)'; b.pct.textContent = '—'; b.pct.__v = undefined; b.bar.set(0); b.note.textContent = ''; }
      }
      if (lim.five_hour || lim.seven_day) {
        b5.cap.textContent = '5-hour limit'; bw.cap.textContent = 'Weekly limit';
        fill(b5, lim.five_hour, lim.five_hour && lim.five_hour.reset ? 'Resets in ' + UI.fmtLeft(lim.five_hour.reset - now) : '');
        fill(bw, lim.seven_day, lim.seven_day && lim.seven_day.reset ? resetWeekly(lim.seven_day.reset) : '');
      } else {   // no plan limits reported: show today's usage instead
        var t = a.today || {}; b5.cap.textContent = 'Tokens today'; bw.cap.textContent = 'Messages';
        b5.pct.style.color = 'var(--text)'; b5.pct.textContent = UI.fmtTok(t.tokens); b5.pct.__v = undefined; b5.bar.set(0); b5.note.textContent = 'Output ' + UI.fmtTok(t.output);
        bw.pct.style.color = 'var(--text)'; bw.pct.textContent = String(t.messages || 0); bw.pct.__v = undefined; bw.bar.set(0); bw.note.textContent = 'Last hour ' + UI.fmtTok(a.last_hour);
      }
    } };
  };

  // ================================================================== Calendar
  var calSig = '';
  function evDay(d) {
    var today = new Date(), tom = new Date(today.getTime() + 86400000), k = d.toDateString();
    return k === today.toDateString() ? 'Today' : k === tom.toDateString() ? 'Tomorrow' : UI.days[d.getDay()];
  }
  P.calendar = {
    icon: 'event', label: 'Calendar', key: 'calendar', kinds: ['events'],
    build: function (root) {
      var page = el('div', 'cal scroll'); page.style.height = '100%'; page.appendChild(el('div', 'cal-title', 'Upcoming'));
      var list = el('div'); page.appendChild(list); root.appendChild(page);
      P.calendar.update = function () {
        var e = S.events; if (!e) { return; }
        var sig = JSON.stringify(e.events) + e.days; if (sig === calSig) { return; } calSig = sig;
        clear(list); var last = '', cards = [], today = new Date().toDateString();
        e.events.forEach(function (ev) {
          var d = new Date(ev.start * 1000), key = d.toDateString();
          if (key !== last) {
            last = key; var h = el('div', 'cal-day', (evDay(d) === 'Today' ? 'TODAY' : evDay(d).toUpperCase()) + '  •  ' + UI.dateLong(d));
            h.style.color = key === today ? 'var(--amber)' : 'var(--muted)'; list.appendChild(h);
          }
          var row = el('div', 'card cal-ev'), bar = el('div', 'bar-v'), when = el('div', 'when'), body = el('div', 'grow');
          bar.style.background = ev.color || 'var(--blue)';
          if (ev.all_day) { when.textContent = 'All day'; } else { when.appendChild(el('div', null, UI.timeText(d))); when.appendChild(el('div', null, UI.timeText(new Date(ev.end * 1000)))); }
          body.appendChild(el('div', 'what ell', ev.title));
          var more = [ev.loc, ev.cal].filter(function (x) { return x; }).join('  •  '); if (more) { body.appendChild(el('div', 'where ell', more)); }
          row.appendChild(bar); row.appendChild(when); row.appendChild(body); list.appendChild(row); cards.push(row);
        });
        list.appendChild(el('div', 'cal-empty', e.events.length ? 'No more events in the next ' + (e.days || 7) + ' days' : 'No events in the next ' + (e.days || 7) + ' days'));
        UI.rise(cards);
      };
      P.calendar.update();
    }
  };
  B.events = function (card, it) {
    card.className += ' w-events'; card.appendChild(el('div', 'cap', 'Up next')); var list = el('div'); card.appendChild(list); UI.loading(card);
    var rows = it.h >= 2 ? 3 : 1;
    return { kind: 'events', update: function () {
      var e = S.events; if (!e) { return; } UI.ready(card); clear(list);
      if (!e.events.length) { list.appendChild(el('div', 'sub', 'No more events in the next ' + (e.days || 7) + ' days')); list.firstChild.style.marginTop = '.5rem'; return; }
      e.events.slice(0, rows).forEach(function (ev) {
        var d = new Date(ev.start * 1000), row = el('div', 'evrow'), bar = el('div', 'evbar'), body = el('div', 'grow');
        bar.style.background = ev.color || 'var(--blue)'; body.appendChild(el('div', 'evt ell', ev.title));
        body.appendChild(el('div', 'evs', evDay(d) + '  •  ' + (ev.all_day ? 'All day' : UI.timeText(d)))); row.appendChild(bar); row.appendChild(body); list.appendChild(row);
      });
    } };
  };

  // ================================================================== Weather
  P.weather = {
    icon: 'wb_sunny', label: 'Weather', key: 'weather', kinds: ['weather'],
    build: function (root) {
      var page = el('div', 'wx-page'), now = cardOf(null, 'wx-now'), big = el('span', 'mi big-i', 'cloud'), mid = el('div'), t = el('div', 't', '-'), c = el('div', 'c'), p = el('div', 'p');
      mid.appendChild(t); mid.appendChild(c); mid.appendChild(p);
      var side = el('div', 'side'), s1 = el('div'), s2 = el('div'), s3 = el('div'), upd = el('div', 'upd'); side.appendChild(s1); side.appendChild(s2); side.appendChild(s3); side.appendChild(upd);
      now.appendChild(big); now.appendChild(mid); now.appendChild(side); UI.loading(now);
      var hours = cardOf(null, 'wx-hours'), hcells = [], i;
      for (i = 0; i < 24; i++) { var h = el('div', 'wx-hour'), hl = el('div', 'h'), hi = icon('cloud'), ht = el('div'); h.appendChild(hl); h.appendChild(hi); h.appendChild(ht); hours.appendChild(h); hcells.push({ l: hl, i: hi, t: ht, box: h }); }
      UI.loading(hours);
      var days = cardOf(null, 'wx-days'), dcells = [];
      for (i = 0; i < 6; i++) { var d = el('div', 'wx-day'), dl = el('div', 'd'), di = icon('cloud'), dt = el('div'), dp = el('div', 'pr'); d.appendChild(dl); d.appendChild(di); d.appendChild(dt); d.appendChild(dp); days.appendChild(d); dcells.push({ l: dl, i: di, t: dt, p: dp, box: d }); }
      UI.loading(days);
      var hint = cardOf(null); hint.style.display = 'none'; hint.appendChild(el('div', 'cap', 'Weather is not set up'));
      var hp = el('div', 'sub', 'On the PC, add this to config.toml and restart the companion:'); hp.style.margin = '.5rem 0'; hint.appendChild(hp);
      var code = el('div', null, '[weather]\ncity = "Your city"'); code.style.whiteSpace = 'pre'; code.style.fontSize = '1rem'; hint.appendChild(code);
      page.appendChild(now); page.appendChild(hours); page.appendChild(days); page.appendChild(hint); root.appendChild(page);
      UI.rise([now, hours, days]);
      P.weather.update = function () {
        var w = S.msg.weather; if (!w) { return; }
        if (w.error) { [now, hours, days].forEach(function (n) { n.style.display = 'none'; }); hint.style.display = ''; return; }
        [now, hours, days].forEach(function (n) { n.style.display = ''; UI.ready(n); }); hint.style.display = 'none';
        var cur = UI.weather(w.code, w.is_day); big.textContent = cur.i; big.style.color = cur.c;
        UI.tween(t, w.temp, deg); c.textContent = cur.t; p.textContent = w.place;
        s1.textContent = 'Feels like ' + deg(w.feels); s2.textContent = 'Humidity ' + w.humidity + '%'; s3.textContent = 'Wind ' + w.wind + ' ' + w.wind_unit;
        upd.textContent = 'Updated ' + UI.timeText(new Date(w.fetched * 1000));
        hcells.forEach(function (cell, k) {
          var hh = w.hours[k]; cell.box.style.display = hh ? '' : 'none'; if (!hh) { return; }
          var d = new Date(hh.t * 1000), hr = d.getHours(), wi = UI.weather(hh.code, hr >= 7 && hr < 20);
          cell.l.textContent = k === 0 ? 'Now' : hourLabel(d); cell.i.textContent = wi.i; cell.i.style.color = wi.c; cell.t.textContent = deg(hh.temp);
        });
        dcells.forEach(function (cell, k) {
          var dd = w.days[k]; cell.box.style.display = dd ? '' : 'none'; if (!dd) { return; }
          var d = new Date(dd.t * 1000), wi = UI.weather(dd.code, true);
          cell.l.textContent = k === 0 ? 'Today' : UI.dayShort(d.getDay()); cell.i.textContent = wi.i; cell.i.style.color = wi.c;
          cell.t.textContent = deg(dd.hi) + ' / ' + deg(dd.lo); cell.p.textContent = dd.precip >= 20 ? dd.precip + '%' : '';
        });
      };
      P.weather.update();
    }
  };
  B.weather = function (card) {
    card.className += ' w-weather'; var ic = el('span', 'mi', 'cloud'), box = el('div'), t = el('div', 't', '-'), d = el('div', 'd'), hl = el('div', 'hl');
    box.appendChild(t); box.appendChild(d); box.appendChild(hl); card.appendChild(ic); card.appendChild(box); UI.loading(card);
    return { kind: 'weather', update: function () {
      var w = S.msg.weather; if (!w) { return; } UI.ready(card);
      if (w.error) { t.textContent = '-'; d.textContent = 'Not set up'; hl.textContent = 'Add [weather] to config.toml'; return; }
      var cur = UI.weather(w.code, w.is_day); ic.textContent = cur.i; ic.style.color = cur.c; UI.tween(t, w.temp, deg); d.textContent = cur.t;
      hl.textContent = w.days && w.days[0] ? 'H ' + deg(w.days[0].hi) + '   L ' + deg(w.days[0].lo) : w.place;
    } };
  };

  // ================================================================== Media
  function mediaCmd(cmd, value) {
    D.send({ type: 'media', cmd: cmd, value: value || 0 });
    if (cmd === 'toggle' && S.media) { S.media.playing = !S.media.playing; S.mediaAt = Date.now(); if (P.media.update) { P.media.update(); } D.refresh('media'); }
  }
  function mpos(m) { var p = m.pos + (m.playing ? (Date.now() - S.mediaAt) / 1000 : 0); return m.dur > 0 ? Math.min(p, m.dur) : p; }
  function clk(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ':' + pad(sec % 60); }
  P.media = {
    icon: 'music_note', label: 'Media', key: 'media', kinds: ['media'],
    build: function (root) {
      var page = el('div', 'media-page'), art = el('div', 'media-art'), img = el('img'), ph = icon('music_note'), info = el('div', 'media-info');
      art.appendChild(ph); art.appendChild(img);
      var src = el('div', 'media-src'), title = el('div', 'media-title', 'Nothing playing'), artist = el('div', 'media-artist'), album = el('div', 'media-album');
      var seek = el('div', 'seekbar'), bar = UI.bar(), knob = el('div', 'knob'); seek.appendChild(bar.root); seek.appendChild(knob);
      var times = el('div', 'times'), tp = el('span', null, '0:00'), td = el('span', null, '0:00'); times.appendChild(tp); times.appendChild(td);
      var ctrls = el('div', 'ctrls'), prev = el('button', 'cbtn'), play = el('button', 'cbtn big'), next = el('button', 'cbtn'), pi = icon('play_arrow');
      prev.appendChild(icon('skip_previous')); play.appendChild(pi); next.appendChild(icon('skip_next')); ctrls.appendChild(prev); ctrls.appendChild(play); ctrls.appendChild(next);
      [src, title, artist, album, seek, times, ctrls].forEach(function (n) { info.appendChild(n); }); page.appendChild(art); page.appendChild(info); root.appendChild(page);
      prev.onclick = function () { mediaCmd('prev'); }; next.onclick = function () { mediaCmd('next'); }; play.onclick = function () { mediaCmd('toggle'); };
      seek.onclick = function (ev) { var m = S.media; if (!m || !m.can_seek || !m.dur) { return; } var r = seek.getBoundingClientRect(); mediaCmd('seek', Math.round((ev.clientX - r.left) / r.width * m.dur)); };
      var artId = -1, tick = null;
      function paint(animate) {
        var m = S.media;
        if (!m || !m.active) { src.textContent = ''; title.textContent = 'Nothing playing'; artist.textContent = ''; album.textContent = ''; bar.set(0); knob.style.left = '0'; tp.textContent = td.textContent = '0:00'; pi.textContent = 'play_arrow'; setCls(art, 'media-art paused'); return; }
        src.textContent = m.source || ''; title.textContent = m.title || '-'; artist.textContent = m.artist || ''; album.textContent = m.album || '';
        pi.textContent = m.playing ? 'pause' : 'play_arrow'; setCls(art, 'media-art' + (m.playing ? '' : ' paused'));
        var p = mpos(m), f = m.dur > 0 ? p / m.dur * 100 : 0; bar.set(f); knob.style.left = f + '%'; tp.textContent = clk(p); td.textContent = clk(m.dur || 0);
      }
      P.media.update = function () {
        var m = S.media; if (!m) { return; }
        var id = m.active ? (m.art_id || 0) : 0;
        if (id !== artId) { artId = id; D.image(img, id ? '/art/' + id : ''); ph.style.display = id ? 'none' : ''; }
        paint();
      };
      P.media.sync = function () {   // the progress bar moves once a second, only while this page is open and something plays
        var need = D.page() === 'media' && !document.hidden && S.media && S.media.playing && D.cfg.mode !== 'ultra';
        if (need && !tick) { tick = setInterval(function () { paint(); }, 1000); } else if (!need && tick) { clearInterval(tick); tick = null; }
      };
      P.media.update();
    }
  };
  B.media = function (card) {
    card.className += ' w-media'; var cover = el('div', 'cover'), img = el('img'), ph = icon('music_note'), box = el('div', 'grow'), title = el('div', 'evt ell', 'Nothing playing'), sub = el('div', 'evs ell'), btn = el('button', 'cbtn'), pi = icon('play_arrow');
    cover.appendChild(ph); cover.appendChild(img); box.appendChild(title); box.appendChild(sub); btn.appendChild(pi); card.appendChild(cover); card.appendChild(box); card.appendChild(btn); UI.loading(card);
    btn.onclick = function () { mediaCmd('toggle'); }; var artId = -1;
    return { kind: 'media', update: function () {
      var m = S.media; if (!m) { return; } UI.ready(card);
      var id = m.active ? (m.art_id || 0) : 0; if (id !== artId) { artId = id; D.image(img, id ? '/art/' + id : ''); ph.style.display = id ? 'none' : ''; }
      if (!m.active) { title.textContent = 'Nothing playing'; sub.textContent = ''; pi.textContent = 'play_arrow'; return; }
      title.textContent = m.title || '-'; sub.textContent = m.artist || m.source || ''; pi.textContent = m.playing ? 'pause' : 'play_arrow';
    } };
  };

  // ================================================================== Shortcut keys
  var keySig = '';
  P.keys = {
    icon: 'grid_view', label: 'Shortcuts', key: 'shortcuts', kinds: ['tiles', 'tile_state'],
    build: function (root) {
      var grid = el('div', 'keys scroll'); grid.style.height = '100%'; root.appendChild(grid); var btns = [];
      P.keys.update = function (kind) {
        var sig = JSON.stringify(S.tiles);
        if (sig !== keySig) {
          keySig = sig; clear(grid); btns = [];
          S.tiles.forEach(function (t, i) {
            var b = el('button', 'key'), ic = icon(t.icon || 'apps'); ic.style.color = UI.tint(t.color, .5);
            b.appendChild(ic); b.appendChild(el('span', 'nm ell', t.label));
            b.onclick = function () { D.send({ type: 'shortcut', id: i }); b.className = b.className.replace(' pulse', '') + ' pulse'; setTimeout(function () { b.className = b.className.replace(' pulse', ''); }, 520); };
            grid.appendChild(b); btns.push(b);
          });
          if (!S.tiles.length) { grid.appendChild(el('div', 'sub', 'No shortcut buttons are set up on the PC yet.')); }
          UI.rise(btns);
        }
        btns.forEach(function (b, i) { b.className = 'key' + (S.lit.indexOf(i) >= 0 ? ' lit' : ''); });
      };
      P.keys.update();
    }
  };

  // ================================================================== Timer (works without the PC)
  var T = { end: 0, paused: 0, total: 0 }, sel = parseInt(D.load('dh_timer_min', '25'), 10) || 25, tp = null, tickTimer = null, endTimer = null, audio = null, beepTimer = null;
  try { var saved = JSON.parse(D.load('dh_timer', 'null')); if (saved && typeof saved.end === 'number') { T = saved; } } catch (e) { /* fresh */ }
  function saveT() { D.save('dh_timer', JSON.stringify(T)); }
  function running() { return T.end > 0; }
  function remaining() { return running() ? Math.max(0, T.end - Date.now()) : T.paused; }
  function active() { return running() || T.paused > 0; }
  function mmss(ms) { var s = Math.ceil(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); s = s % 60; return (h ? h + ':' + pad(m) : pad(m)) + ':' + pad(s); }
  function beepOnce() {
    try {
      if (audio) { var o = audio.createOscillator(), g = audio.createGain(); o.frequency.value = 880; g.gain.value = 0.25; o.connect(g); g.connect(audio.destination); o.start(); o.stop(audio.currentTime + 0.25); }
      if (navigator.vibrate) { navigator.vibrate([300, 150, 300]); }
    } catch (e) { /* no sound */ }
  }
  function ring() {
    D.wake(); var ov = document.getElementById('timer-alert'); if (ov) { ov.className = 'overlay top on'; }
    var n = 0; clearInterval(beepTimer); beepOnce(); beepTimer = setInterval(function () { beepOnce(); if (++n > 25) { clearInterval(beepTimer); } }, 2000);
  }
  function stopRing() { clearInterval(beepTimer); var ov = document.getElementById('timer-alert'); if (ov) { ov.className = 'overlay top'; } }
  function finish() { T = { end: 0, paused: 0, total: 0 }; saveT(); schedule(); ring(); render(true); D.updateNav(); }
  function schedule() {
    clearTimeout(endTimer); clearInterval(tickTimer);
    if (running()) {
      endTimer = setTimeout(function () { if (remaining() <= 0) { finish(); } else { schedule(); } }, Math.max(50, T.end - Date.now() + 20));
      // the time left once a second while its page is open, the tab label every 15 s otherwise
      tickTimer = setInterval(function () { if (D.page() === 'timer') { render(); } else { D.updateNav(); } }, D.page() === 'timer' ? 1000 : 15000);
    }
  }
  function begin(ms) {
    try { var AC = window.AudioContext || window.webkitAudioContext; if (AC && !audio) { audio = new AC(); } if (audio && audio.resume) { audio.resume(); } } catch (e) { /* silent timer */ }
    T = { end: Date.now() + ms, paused: 0, total: ms }; saveT(); schedule(); render(); D.updateNav();
  }
  function render(done) {
    if (!tp) { return; }
    var rem = active() ? remaining() : sel * 60000, total = T.total || sel * 60000;
    tp.time.textContent = mmss(rem); tp.ring.set(done ? 0 : rem / total * 100);
    tp.st.textContent = running() ? 'Running' : T.paused > 0 ? 'Paused' : done ? 'Time’s up' : 'Ready';
    tp.play.firstChild.textContent = running() ? 'pause' : 'play_arrow';
    var i; for (i = 0; i < tp.presets.length; i++) { tp.presets[i].b.className = 'preset' + (tp.presets[i].m === sel && !active() ? ' on' : ''); }
  }
  P.timer = {
    icon: 'timer', label: 'Timer', key: 'timer', kinds: [],
    navLabel: function () { return active() ? Math.max(1, Math.ceil(remaining() / 60000)) + 'm' : null; },
    show: function () { render(); schedule(); }, hide: function () { schedule(); },
    build: function (root) {
      var page = el('div', 'timer-page'), main = cardOf(null, 'timer-main'), wrap = el('div', 'ring'), r = UI.ring(true, 8), c = el('div', 'ring-center'), tm = el('div', 'num', '25:00'), st = el('div', 'st', 'Ready');
      c.appendChild(tm); c.appendChild(st); wrap.appendChild(r.svg); wrap.appendChild(c); main.appendChild(wrap);
      var side = cardOf('Minutes', 'timer-side'), grid = el('div', 'presets'), presets = [];
      [1, 5, 10, 15, 25, 45].forEach(function (m) { var b = el('button', 'preset', String(m)); b.onclick = function () { if (!active()) { sel = m; D.save('dh_timer_min', String(m)); render(); } }; grid.appendChild(b); presets.push({ m: m, b: b }); });
      var act = el('div', 'timer-actions'), reset = el('button', 'cbtn'), play = el('button', 'cbtn big amber');
      reset.appendChild(icon('restart_alt')); play.appendChild(icon('play_arrow')); act.appendChild(reset); act.appendChild(play);
      side.appendChild(grid); side.appendChild(act); page.appendChild(main); page.appendChild(side); root.appendChild(page);
      play.onclick = function () {
        if (running()) { T.paused = remaining(); T.end = 0; saveT(); schedule(); }
        else if (T.paused > 0) { T.end = Date.now() + T.paused; T.paused = 0; saveT(); schedule(); }
        else { begin(sel * 60000); return; }
        render(); D.updateNav();
      };
      reset.onclick = function () { T = { end: 0, paused: 0, total: 0 }; saveT(); schedule(); render(); D.updateNav(); };
      tp = { time: tm, ring: r, st: st, play: play, presets: presets };
      var ov = el('div', 'overlay top'), box = el('div', 'box'), b2 = el('button', 'btn', 'Dismiss'); ov.id = 'timer-alert';
      box.appendChild(el('h2', null, 'Time’s up')); box.appendChild(b2); ov.appendChild(box); b2.onclick = stopRing; document.getElementById('app').appendChild(ov);
      if (running() && T.end <= Date.now()) {   // ended while the page was closed: ring only if it ended moments ago
        var late = Date.now() - T.end; T = { end: 0, paused: 0, total: 0 }; saveT(); if (late < 120000) { ring(); }
      }
      schedule(); render();
    }
  };
  document.addEventListener('visibilitychange', function () {   // the screen was off: timers did not run
    if (!document.hidden && running()) { if (remaining() <= 0) { finish(); } else { schedule(); render(); } }
  });
})();
