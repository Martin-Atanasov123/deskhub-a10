/* Sample data for looking at the design without a PC: open the dashboard with ?demo=1
   (add &ai=codex for the Codex colours, &page=ai to open a page). Nothing is sent anywhere. ES5 on purpose. */
(function () {
  'use strict';
  var D = window.DH, q = location.search;
  function arg(name, dflt) { var m = new RegExp('[?&]' + name + '=([^&]*)').exec(q); return m ? decodeURIComponent(m[1]) : dflt; }
  var codex = arg('ai', 'claude') === 'codex', now = Math.floor(Date.now() / 1000), seed = 7;
  function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }

  function layout() { return { type: 'layout', pages: ['ai', 'stats', 'calendar', 'weather', 'media', 'shortcuts', 'timer', 'printer', 'games', 'github', 'network'], ordered: true, nav: 'left', pc_sleep: 'off', night_start: -1, night_end: -1, night_style: 'dim' }; }
  function ai() {
    var days = codex ? [3.1e6, 5.4e6, 2.2e6, 8.8e6, 4.1e6, 6.3e6, 5.2e6] : [12.4e6, 31.2e6, 18.9e6, 44.5e6, 27.3e6, 52.8e6, 38.6e6];
    return { type: 'ai', provider: codex ? 'codex' : 'claude',
      limits: { five_hour: { pct: codex ? 23 : 46, reset: now + 2 * 3600 + 14 * 60 }, seven_day: { pct: codex ? 61 : 87, reset: now + 3 * 86400 + 5 * 3600 } },
      today: codex ? { tokens: 5.2e6, output: 310e3, messages: 38 } : { tokens: 38.6e6, output: 412e3, messages: 214 }, last_hour: codex ? 640e3 : 5.8e6, days: days,
      models: codex ? [{ name: 'gpt-5-codex', tokens: 4.4e6 }, { name: 'gpt-5-mini', tokens: 0.8e6 }]
                    : [{ name: 'claude-fable-5-2', tokens: 21.7e6 }, { name: 'claude-opus-5-5', tokens: 12.1e6 }, { name: 'claude-sonnet-5-5', tokens: 4.1e6 }, { name: 'claude-haiku-5-5', tokens: 0.7e6 }] };
  }
  function stats(t) { return { type: 'stats', cpu: Math.round(26 + 20 * Math.sin(t / 5) + rnd() * 8), gpu: Math.round(46 + 30 * Math.sin(t / 7 + 1) + rnd() * 6), gpu_temp: 61, ram_used: 21.4, ram_total: 32, vram_used: 7.2, vram_total: 12,
    net_down: 840, net_up: 95, disk: 63, cpu_name: 'Ryzen 7 5800X', gpu_name: 'RTX 3070' }; }
  function net() {
    var h = [], i; for (i = 0; i < 60; i++) { h.push(Math.round(14 + rnd() * 10 + (i === 33 ? 60 : 0))); }
    return { type: 'net', online: true, latency_ms: 18, jitter_ms: 2.4, loss_pct: 0, up_since: now - 3 * 86400 - 5 * 3600, last_drop: { at: now - 2 * 86400 }, today_bytes: 6.2e9, month_bytes: 188e9, hist: h, testing: false,
      speed: { down_mbps: 482, up_mbps: 96, ping_ms: 11, at: now - 4 * 3600 } };
  }
  function events() {
    var d = new Date(); d.setHours(0, 0, 0, 0); var t0 = Math.floor(d.getTime() / 1000);
    return { type: 'events', days: 7, events: [
      { title: 'Design review', start: now + 3600, end: now + 5400, color: '#62b0f5', loc: 'Room 4', cal: 'Work' },
      { title: 'Dentist', start: now + 6 * 3600, end: now + 7 * 3600, color: '#f08ec9', loc: 'Clinic', cal: 'Personal' },
      { title: 'Pay rent', start: t0 + 86400, end: t0 + 2 * 86400, all_day: true, color: '#fbb024', cal: 'Home' },
      { title: 'Football with friends', start: t0 + 86400 + 19 * 3600, end: t0 + 86400 + 21 * 3600, color: '#34d58a', loc: 'City park', cal: 'Personal' }] };
  }
  function weather() {
    var hours = [], days = [], i; for (i = 0; i < 24; i++) { hours.push({ t: now + i * 3600, code: i < 6 ? 1 : i < 12 ? 2 : i < 16 ? 61 : 3, temp: Math.round(14 + 8 * Math.sin((i - 8) / 24 * 6.28)) }); }
    var codes = [2, 61, 3, 0, 1, 95]; for (i = 0; i < 6; i++) { days.push({ t: now + i * 86400, code: codes[i], hi: 22 - i, lo: 11 + (i % 3), precip: codes[i] === 61 || codes[i] === 95 ? 60 : 5 }); }
    return { type: 'weather', place: 'Sample City', fetched: now - 600, code: 2, is_day: true, temp: 19, feels: 18, humidity: 54, wind: 11, wind_unit: 'km/h', hours: hours, days: days };
  }
  function media() { return { type: 'media', active: true, playing: true, title: 'Midnight City', artist: 'M83', album: "Hurry Up, We're Dreaming", source: 'Spotify', pos: 74, dur: 243, can_seek: true, art_id: 1 }; }
  function printer() {
    return { type: 'printer', printers: [
      { name: 'Bambu P1S', model: 'P1S', online: true, state: 'RUNNING', pct: 64, remaining_min: 95, layer: 112, layers: 175, file: 'benchy_0.2mm_PLA.3mf', speed: 'Standard', error: '', nozzle: 219, nozzle_target: 220, bed: 59, bed_target: 60, chamber: 34,
        ams: [{ color: '#f2f2f2', type: 'PLA', active: true }, { color: '#e5493a', type: 'PETG', active: false }, { color: '#2f6bff', type: 'PLA', active: false }, { color: '#222222', type: 'ABS', active: false }] },
      { name: 'Ender 3', model: 'Marlin', online: true, state: 'IDLE', pct: 0, remaining_min: 0, layer: 0, layers: 0, file: '', speed: '', error: '', nozzle: 24, nozzle_target: 0, bed: 23, bed_target: 0, chamber: null, ams: [] }] };
  }
  function steam() {
    return { type: 'steam', found: true, friends: [{ name: 'Alex' }], playing: { appid: 570, name: 'Dota 2', session_s: 2820, total_min: 18400 },
      recent: [{ appid: 730, name: 'Counter-Strike 2', total_min: 9200 }, { appid: 1245620, name: 'Elden Ring', total_min: 4380 }, { appid: 1091500, name: 'Cyberpunk 2077', total_min: 2900 }, { appid: 271590, name: 'Grand Theft Auto V', total_min: 1500 }, { appid: 105600, name: 'Terraria', total_min: 760 }] };
  }
  function github() {
    var n = 371, lv = '', i, d = new Date(), start = new Date(d.getTime() - (n - 1) * 86400000), months = [], lastM = -1, sw = start.getDay(), names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    for (i = 0; i < n; i++) {
      var r = rnd(), wd = (i + sw) % 7; lv += (wd === 0 || wd === 6) ? (r < .6 ? 0 : r < .85 ? 1 : 2) : (r < .15 ? 0 : r < .4 ? 1 : r < .65 ? 2 : r < .88 ? 3 : 4);
      var dt = new Date(start.getTime() + i * 86400000); if (dt.getMonth() !== lastM && dt.getDate() <= 7 && wd === 0 || (i === 0)) { if (dt.getMonth() !== lastM) { lastM = dt.getMonth(); months.push([Math.floor((i + sw) / 7), names[lastM]]); } }
    }
    return { type: 'github', login: 'demo', total: 1842, levels: lv, start_wday: sw, months: months, kinds: { commits: 1620, issues: 46, private: 310 }, streak: 23, longest: 61, best: 38, best_date: 'Mar 12',
      week: 41, last_week: 33, week_days: [3, 8, 11, 6, 9, 4], last_week_days: [5, 2, 9, 7, 6, 3, 1], repos: [{ name: 'deskhub-a10', count: 212 }, { name: 'uni-put', count: 148 }, { name: 'portfolio', count: 77 }, { name: 'dotfiles', count: 31 }] };
  }
  function tiles() {
    return { type: 'tiles', tiles: [{ label: 'Mute', icon: 'mic_off', color: '#f08ec9' }, { label: 'Screenshot', icon: 'screenshot_monitor', color: '#62b0f5' }, { label: 'Lock PC', icon: 'lock', color: '#fbb024' }, { label: 'Notes', icon: 'sticky_note_2', color: '#34d58a' },
      { label: 'Terminal', icon: 'terminal', color: '#b69cf7' }, { label: 'Browser', icon: 'language', color: '#5fd3c0' }, { label: 'Play/Pause', icon: 'play_arrow', color: '#ff6b6b' }, { label: 'Volume up', icon: 'volume_up', color: '#62b0f5' }] };
  }

  // Covers are drawn here (a sun over hills), so no request leaves the page in demo mode.
  var PALETTES = [['#2d2a6e', '#7a4a9e', '#f7c874'], ['#5f8f45', '#2f5a2a', '#f4eec2'], ['#4a1a5e', '#b0306e', '#f7c35a'], ['#9fcdee', '#4b78a8', '#f8fbff'], ['#8a3a16', '#3a1a10', '#f8c25a'], ['#16475a', '#0f2a38', '#fbe39a']];
  D.image = function (img, url) {
    img.className = img.className.replace(/\s*\bon\b/, '');
    if (!url) { img.removeAttribute('src'); return; }
    var n = 0, i, p; for (i = 0; i < url.length; i++) { n = (n * 31 + url.charCodeAt(i)) % 9973; } p = PALETTES[n % PALETTES.length];
    var w = /header/.test(url) ? 460 : 300, h = /header/.test(url) ? 215 : 450;
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + w + ' ' + h + '"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + p[0] + '"/><stop offset="1" stop-color="' + p[1] + '"/></linearGradient></defs>' +
      '<rect width="' + w + '" height="' + h + '" fill="url(#g)"/><circle cx="' + w / 2 + '" cy="' + h * 0.38 + '" r="' + Math.min(w, h) * 0.14 + '" fill="' + p[2] + '"/>' +
      '<path d="M0 ' + h * 0.78 + ' L' + w * 0.3 + ' ' + h * 0.58 + ' L' + w * 0.55 + ' ' + h * 0.74 + ' L' + w * 0.8 + ' ' + h * 0.55 + ' L' + w + ' ' + h * 0.72 + ' L' + w + ' ' + h + ' L0 ' + h + ' Z" fill="#0b1220" fill-opacity=".72"/></svg>';
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); img.className += ' on';
  };

  var origStart = D.start;
  D.start = function () {
    origStart({ demo: true });
    // a minute of chart history, so the live chart has a line from the first frame
    var i, t = Date.now() - 60000; for (i = 0; i < 40; i++) { var s = stats(i); D.S.hist.push({ t: t + i * 1500, cpu: s.cpu, gpu: s.gpu }); }
    var feed = [layout(), tiles(), ai(), stats(40), net(), events(), weather(), media(), printer(), steam(), github()], k = 0;
    // Messages arrive one by one, as they do from a real PC, so the loading shimmer and the entrances can be seen.
    (function next() { if (k < feed.length) { D.dispatch(feed[k++]); setTimeout(next, 160); } else { setTimeout(function () { var p = arg('page', ''); if (p && D.pages[p]) { D.show(p); } }, 300); } })();
    var n = 41; setInterval(function () { D.dispatch(stats(n++)); }, 2000);
  };
})();
