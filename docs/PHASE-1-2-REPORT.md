# DeskHub on a Galaxy A10 — Phase 1 (audit) and Phase 2 (architecture choice)

Source audited: `zacharyinserra/deskhub`, HEAD `cc47e77`, cloned to `deskhub-upstream/` (untouched).
Nothing has been built yet. Items marked **[verify]** need the phone itself.

## TL;DR

- The protocol is **plain WebSocket (`ws://`) carrying JSON text frames, plus two binary image frame types**. It is not HTTP polling.
- **The roles are inverted from what a phone needs.** The ESP32 is the WebSocket *server*; the Windows companion is the *client* that dials in and pushes data. A phone browser can only be a client, so the companion must become the server.
- The Windows companion is about 10k lines and **almost all of it is reusable unchanged**. All of `firmware/` (about 7k lines of C/LVGL) is hardware-coupled and gets replaced by a web UI.
- **Recommendation: Option A (web dashboard served by the companion).** No blocker found. Fallback if kiosk behaviour disappoints: a thin Kotlin WebView shell around the same web UI.
- MIT licence: keep the licence text and copyright line. Straightforward.

## 1. How it works today

### Transport and auth
| Aspect | Actual implementation | Source |
| --- | --- | --- |
| Transport | WebSocket on port 80, path `/ws`, unencrypted | `firmware/main/hub_server.c:606`, `:819` |
| Who connects | Companion (client) → ESP32 (server) at `ws://deskhub.local/ws` | `companion/deskhub/__main__.py:110`, `:388` |
| Auth | First frame must be `{"type":"hello","token":…}`; token is a compile-time string compared with `strcmp`. Reply `{"type":"hello_ok","version":…}`. Wrong token → socket closed. Pre-hello frames over 256 bytes are rejected. | `hub_server.c:526-540`, `:616` |
| Concurrency | One companion at a time; a new valid hello kicks the old one | `hub_server.c:530` |
| Liveness | Companion pings every 10 s; board marks the PC offline after 5 s of silence | `__main__.py:389`, `hub_server.c:26` |
| Reconnect | Client-side backoff 2 s → 30 s, fast retry after a link that had worked | `__main__.py:454-469` |
| Frame limit | 300 KB per frame on the board | `hub_server.c:25` |

### Companion → display (push model, each producer is an independent asyncio loop)
| Message `type` | Cadence | Notes |
| --- | --- | --- |
| `stats` | 1 s | psutil + NVML (NVIDIA only) |
| `media` | 1 s | Windows media sessions via WinRT |
| binary `ART1` | on cover change | 12-byte header + RGB565 pixels, 280×280 |
| `ai` / `claude` | 5 s | reads Claude Code / Codex local files |
| `net` | 2 s | latency, loss, speed test |
| `printer` | on change, ≥ every 30 s | 9 printer brands |
| `steam` + binary `STM1` | on change, ≥ every 60 s | covers as RGB565 |
| `github` | 30 s | |
| `events` | 10 min | ICS / CalDAV / iCloud |
| `alert` | 1 s poll, sent on change | Claude Code waiting for the user |
| `tile_state` | on change | mic / speaker mute lit state |
| `layout`, `home`, `tiles`, `pc_power` | on connect (and `pc_power` on change) | config → UI structure |

On every (re)connect the companion replays all cached state (`__main__.py:401-424`). That is the "full snapshot on connect" a new web client needs, already written.

### Display → companion (only five commands)
`media {cmd: toggle|next|prev|seek, value}`, `shortcut {id}`, `speedtest`, `steam_launch {appid}`, `alert_action {id, action: focus|dismiss}`. Handled in `Companion.handle` (`__main__.py:356`). Shortcuts send only an **index**; the PC looks up what to run from `config.toml`, so the display never holds commands. That is a good security property to preserve.

### Firmware-only behaviour (the PC never sees it)
Weather (the board calls Open-Meteo itself, `weather.c`), timer page, page navigation, screensaver, night mode and PC-sleep dimming (driven by the `layout`/`pc_power` fields), OTA, and the debug endpoints `/screenshot`, `/tap`, `/perf`.

## 2. Reuse map

| Component | Verdict | Why |
| --- | --- | --- |
| All producers: `stats`, `media` (data part), `claude_*`, `codex_usage`, `calendar_feed`, `netstats`, `printer*` + 9 brand modules, `steam*`, `github`, `claude_alerts`, `pc_power`, `audio_state`, `shortcuts`, `custom_games` | **Reuse as-is** | Pure data collectors emitting JSON dicts. |
| `pages.py` (page list, 5×3 home grid validation, night/sleep config), `config.example.toml`, setup/CLI tools, tray, tests | **Reuse as-is** | The grid maps directly onto CSS Grid. |
| `Companion.handle()` | **Reuse as-is** | Already parses the five commands from JSON. |
| `Companion.send()` / `session()` / `run()` connection logic | **Modify** | Single choke point (`self.ws`). Becomes a fan-out to N web clients plus the same on-connect replay. Producers do not change. |
| `media.to_rgb565_frame`, `steam._pack565`, `STM1`/`ART1` framing | **Add a web variant** | Browsers want JPEG/PNG, not RGB565. Serve covers over HTTP keyed by the existing `art_id`/`appid`. |
| `text.ascii_fold` | **Make optional for web** | It does `encode("ascii","ignore")`, so Cyrillic or CJK titles come out **empty**. A browser can show real Unicode. |
| `flash_cli.py`, firmware/Wi-Fi/token steps of `setup_cli.py`, `install_startup.py` (partly) | **Not needed / trim** | ESP32 provisioning only. |
| `firmware/*` (ESP-IDF, LVGL 9, `ui*.c` 5.7k lines, board/display/ota/net, `lv_mem_psram`, compiled `logos.c`) | **Tightly hardware-coupled, replace** | 800×480 RGB panel, GT911 touch, CH422G expander, PSRAM allocator, LVGL widgets. Only the *layouts and data models* (`hub_model.h`, screenshots in `docs/screenshots/`) carry over as a spec. |

Size limits in the protocol (16 events, 16 tiles, 4 printers, 5 recent games, string lengths) exist only because of fixed C structs. The web UI can keep them for compatibility or lift them later.

Existing Android-compatible frontend: **none**. The firmware's only HTTP routes are a text `/`, `/screenshot` (BMP), `/tap`, `/perf`, and the OTA upload. `ROADMAP.md` mentions a future local web app, but for editing `config.toml`, not for display. The UI has to be written new.

## 3. Licence and attribution

- Project: **MIT**, "Copyright (c) 2026 Desk Hub contributors". Condition: the copyright notice and permission text must be included in all copies or substantial portions.
- Plan: keep upstream `LICENSE` in our tree, add a `NOTICE`/README credit line naming `zacharyinserra/deskhub`, license our additions under MIT as well.
- Fonts: Inter (SIL OFL 1.1) and Material Icons (Apache 2.0) ship in `firmware/main/fonts/` with their licence texts. Reusing them in a web UI is fine; carry the licence files along and serve the TTFs unmodified.
- **[verify]** `firmware/main/logos.c` / `tools/make_logos.py` embed brand logos (printer vendors, etc.). Copyright of the code is MIT, but the logos are other companies' trademarks; check sources before redistributing a public fork.
- This is a read of the licence text, not legal advice.

## 4. Option A vs Option B

Facts that drive the decision:
- Everything on the wire is already JSON, which a browser parses natively.
- The only hard-to-do-in-a-browser needs are *always-on screen* and *fullscreen*.
- `http://<LAN-IP>` is **not a secure context**, so `navigator.wakeLock` and PWA install/service workers are unavailable. Workarounds exist (below).
- A10: 2 GB RAM, Exynos 7884, 720×1520 at roughly 2× density, so about **760×360 CSS px in landscape** (about 19:9, versus the board's 5:3). **[verify]** on the phone.

| Criterion | A: web dashboard | B: native Kotlin + Compose |
| --- | --- | --- |
| Dev complexity | Low. Vanilla JS + CSS Grid, no build step. One Python module on the PC. | High. Android SDK + Gradle, signing, sideloading, plus the same UI work in Compose. |
| Memory on a 2 GB phone | One browser tab, roughly 100–200 MB. Fine. | Roughly 60–120 MB. Better, but not needed. |
| Performance | Data is about 1 KB/s. Dashboard updates 1–2×/s. Fine if we avoid blur, large shadows and heavy animation. | Slightly smoother. |
| Compatibility | Depends on the WebView version. Probe first; write conservative ES2017 + CSS Grid. | Compose runs on API 21+, but Android 9/11 toolchain quirks add risk. |
| Always-on screen | Developer options → *Stay awake* while charging, plus a NoSleep-style fallback. No wake lock API over plain HTTP. | `FLAG_KEEP_SCREEN_ON`, trivially. |
| Fullscreen / kiosk | Fullscreen needs one tap per launch. Home-screen shortcut helps. Full lock-down needs screen pinning or a kiosk browser. | Real kiosk (lock task), boot auto-start. |
| Discovery | Type the PC's IP once (`.local` is unreliable on Android browsers). | mDNS/NSD possible. |
| Maintenance | One codebase, edit and refresh. UI updates ship from the PC; the phone needs nothing. | App updates mean rebuild and reinstall. |
| Feature parity | Full, including *better* text (Unicode) and larger covers. | Full. |

**Decision: Option A.** No clear technical blocker exists. The truncated line in your brief ("unless there is a clear technical…") reads to me as "…blocker"; the two things that would count are (1) the A10's WebView being too old to run a basic page, and (2) the screen not staying on reliably. Both are testable in minutes with a probe page, and both have a cheap escape hatch: **Option C = a ~100-line Kotlin WebView shell** that loads the same URL and adds keep-screen-on, fullscreen and boot start. That reuses 100% of the web UI.

## 5. Proposed architecture (Option A)

```
Windows PC                                              Galaxy A10
┌─────────────────────────────┐                     ┌──────────────────┐
│ existing producers (unchanged)                    │                  │
│   stats / media / ai / net / printer / steam ...  │  Chrome / Samsung│
│            │ send(msg)                            │  Internet, full  │
│            ▼                                      │  screen          │
│ Companion.send → fan-out hub ◄── ws://PC:8787/ws ─┼─► web UI (JS)    │
│            ▲   hello/token, replay on connect     │   5×3 CSS grid   │
│ Companion.handle (unchanged) ◄── 5 commands ──────┤   pages, timer,  │
│ http://PC:8787/  static UI + /art/<id>.jpg        │   weather (JS)   │
└─────────────────────────────┘                     └──────────────────┘
```

1. **New `companion/deskhub/web_server.py`**: uses the `websockets` library already in `pyproject.toml` (`process_request` serves static files), so **no new dependency**. Same `hello`/`hello_ok` token handshake, same JSON messages, same on-connect replay.
2. **Small refactor of `Companion`**: `self.ws` becomes `self.clients`; `send()` broadcasts; the replay block becomes a reusable `snapshot_messages()`. Keep the ESP32 link behind a config flag so the original behaviour is not broken.
3. **Covers**: `GET /art/<art_id>` and `/steam/<appid>/<kind>` as JPEG; the JSON still carries `art_id`.
4. **Web UI** (`companion/deskhub/web/`): one HTML/CSS/JS page, no framework or build step. Render the existing `home.grid` with CSS Grid. Port the firmware-only features to JS: weather (browser calls Open-Meteo directly), timer, clock, night / PC-sleep dimming from the `layout` and `pc_power` messages.
5. **Client robustness**: auto-reconnect with the same 2→30 s backoff, a 5 s no-data watchdog like the board's, and a visible "PC offline" state.
6. **Security**: bind to the LAN, require the token in `hello`, never accept command strings from the client (the index-based shortcut design already guarantees this). Token goes in the URL **fragment** once, then localStorage; not in the query string. Plain HTTP on a trusted LAN, as upstream does. Windows Firewall needs one inbound rule, scoped to Private + local subnet; I will give you the exact command and not change it myself.
7. **Tests**: extend `tests/fake_hub.py` into a conformance test for the web transport.

### Build order (proposed)
0. Probe page and tiny server → read Android/WebView/DPR/viewport and test keep-awake on your phone. **This settles the open questions.**
1. Transport + Home grid + Stats + Media + Shortcuts (the day-to-day core).
2. Calendar, AI usage, Weather, Timer, Network.
3. Printer, Games, GitHub, Alerts, polish (night mode, themes for 760×360).

## 6. Risks and open items

| Risk | Mitigation |
| --- | --- |
| Phone's WebView is old | Probe in step 0; write ES2017-level JS; no `?.`, `??`, or CSS `inset`/`aspect-ratio` until proven. |
| PC's LAN IP changes (now `192.168.1.25` on the Wi-Fi adapter) | DHCP reservation in the router. |
| Screen sleeps | Developer options → Stay awake; NoSleep fallback; Option C if needed. |
| Old battery on 24/7 charge | Non-removable battery on the A10; swelling risk is real. Consider a smart plug / charge cycling. |
| Windows Firewall blocks the phone | One scoped inbound rule (command provided later, applied only with your OK). |
| Companion is Windows-only (WinRT, pynput, `os.startfile`) | Fine; the host is Windows. |
| Phone's Android and browser versions unknown | The compatibility page (`/compat`) reads everything from the phone's own browser over Wi-Fi and sends it to the PC. |
